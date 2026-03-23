from decimal import Decimal
from datetime import datetime, timezone
import unicodedata

from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from ..models import Bookmaker, Event, Market, Odd


def _latest_side(session: Session, side: str):
    latest = (
        select(
            Odd.market_id,
            Odd.bookmaker_id,
            Odd.outcome,
            func.max(Odd.pulled_at).label("pulled_at"),
        )
        .where(Odd.side == side)
        .group_by(Odd.market_id, Odd.bookmaker_id, Odd.outcome)
        .subquery()
    )

    return (
        select(
            Odd.market_id,
            Odd.bookmaker_id,
            Odd.outcome,
            Odd.price_decimal,
        )
        .join(
            latest,
            and_(
                Odd.market_id == latest.c.market_id,
                Odd.bookmaker_id == latest.c.bookmaker_id,
                Odd.outcome == latest.c.outcome,
                Odd.pulled_at == latest.c.pulled_at,
            ),
        )
        .subquery()
    )


def _back_lay_math(back_odds: Decimal, lay_odds: Decimal, commission: Decimal) -> dict:
    if lay_odds <= commission:
        return {}
    # For back stake 1.0
    lay_stake = back_odds / (lay_odds - commission)
    profit_win = (back_odds - Decimal(1)) - lay_stake * (lay_odds - Decimal(1))
    profit_lose = -Decimal(1) + lay_stake * (Decimal(1) - commission)
    return {
        "lay_stake": lay_stake,
        "profit_win": profit_win,
        "profit_lose": profit_lose,
        "min_profit": min(profit_win, profit_lose),
    }


def _normalize_team(value: str) -> str:
    base = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in base if ch.isalnum() or ch.isspace())
    tokens = stripped.lower().split()
    if len(tokens) > 1:
        stop = {
            "fc",
            "fk",
            "if",
            "ifk",
            "aik",
            "bk",
            "sk",
            "ik",
            "cf",
            "ac",
            "sc",
            "afc",
            "sv",
        }
        tokens = [t for t in tokens if t not in stop]
    token_map = {
        "munich": "munchen",
        "munchen": "munchen",
        "prague": "prag",
        "prag": "prag",
        "paphos": "pafos",
        "pafos": "pafos",
    }
    normalized = [token_map.get(t, t) for t in tokens]
    return " ".join(normalized)


def _time_bucket(value: datetime | None, minutes: int = 60) -> int | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    seconds = int(value.timestamp())
    bucket = minutes * 60
    return seconds // bucket


def _normalize_spec(market_type: str, spec: str | None) -> str:
    market_type = (market_type or "").strip().upper()
    raw = (spec or "").strip().lower()
    raw = " ".join(raw.split())
    raw = raw.replace("–", "-")

    if market_type == "1X2":
        return "full_time"
    if market_type == "BTTS":
        return "btts"
    if raw in {"full time", "fulltime", "fulltid"}:
        return "full_time"
    if raw in {"båda lagen gör mål", "both teams to score", "btts"}:
        return "btts"
    return raw or "unknown"


def _latest_side_rows(session: Session, side: str) -> list[dict]:
    latest = (
        select(
            Odd.market_id,
            Odd.bookmaker_id,
            Odd.outcome,
            func.max(Odd.pulled_at).label("pulled_at"),
        )
        .where(Odd.side == side)
        .group_by(Odd.market_id, Odd.bookmaker_id, Odd.outcome)
        .subquery()
    )

    rows = session.execute(
        select(
            Odd.market_id,
            Odd.bookmaker_id,
            Odd.outcome,
            Odd.price_decimal,
            Market.market_type,
            Market.spec,
            Event.home_team,
            Event.away_team,
            Event.start_time,
            Bookmaker.name.label("bookmaker"),
        )
        .join(
            latest,
            and_(
                Odd.market_id == latest.c.market_id,
                Odd.bookmaker_id == latest.c.bookmaker_id,
                Odd.outcome == latest.c.outcome,
                Odd.pulled_at == latest.c.pulled_at,
            ),
        )
        .join(Market, Market.id == Odd.market_id)
        .join(Event, Event.id == Market.event_id)
        .join(Bookmaker, Bookmaker.id == Odd.bookmaker_id)
    ).all()

    return [
        {
            "market_id": row.market_id,
            "bookmaker_id": row.bookmaker_id,
            "bookmaker": row.bookmaker,
            "outcome": row.outcome,
            "odds": Decimal(row.price_decimal),
            "market_type": row.market_type,
            "spec": row.spec,
            "home": row.home_team,
            "away": row.away_team,
            "start_time": row.start_time,
        }
        for row in rows
    ]


def find_back_lay_arbs(
    session: Session,
    commission_rate: Decimal,
    allow_same_bookmaker: bool = False,
    match_events: bool = True,
) -> list[dict]:
    if match_events:
        return find_back_lay_arbs_cross_event(
            session, commission_rate, allow_same_bookmaker=allow_same_bookmaker
        )
    back_latest = _latest_side(session, "back")
    lay_latest = _latest_side(session, "lay")

    back_ranked = (
        select(
            back_latest.c.market_id,
            back_latest.c.outcome,
            back_latest.c.price_decimal,
            back_latest.c.bookmaker_id,
            func.row_number()
            .over(
                partition_by=[back_latest.c.market_id, back_latest.c.outcome],
                order_by=back_latest.c.price_decimal.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )

    lay_ranked = (
        select(
            lay_latest.c.market_id,
            lay_latest.c.outcome,
            lay_latest.c.price_decimal,
            lay_latest.c.bookmaker_id,
            func.row_number()
            .over(
                partition_by=[lay_latest.c.market_id, lay_latest.c.outcome],
                order_by=lay_latest.c.price_decimal.asc(),
            )
            .label("rn"),
        )
        .subquery()
    )

    BackBookmaker = aliased(Bookmaker)
    LayBookmaker = aliased(Bookmaker)

    query = (
        select(
            back_ranked.c.market_id,
            back_ranked.c.outcome,
            back_ranked.c.price_decimal.label("back_odds"),
            back_ranked.c.bookmaker_id.label("back_bookmaker_id"),
            lay_ranked.c.price_decimal.label("lay_odds"),
            lay_ranked.c.bookmaker_id.label("lay_bookmaker_id"),
            BackBookmaker.name.label("back_bookmaker"),
            LayBookmaker.name.label("lay_bookmaker"),
        )
        .join(BackBookmaker, BackBookmaker.id == back_ranked.c.bookmaker_id)
        .join(
            lay_ranked,
            and_(
                back_ranked.c.market_id == lay_ranked.c.market_id,
                back_ranked.c.outcome == lay_ranked.c.outcome,
                lay_ranked.c.rn == 1,
            ),
        )
        .join(LayBookmaker, LayBookmaker.id == lay_ranked.c.bookmaker_id)
        .where(back_ranked.c.rn == 1)
    )

    if not allow_same_bookmaker:
        query = query.where(back_ranked.c.bookmaker_id != lay_ranked.c.bookmaker_id)

    rows = session.execute(query).all()

    results = []
    for row in rows:
        math = _back_lay_math(
            Decimal(row.back_odds),
            Decimal(row.lay_odds),
            commission_rate,
        )
        if not math:
            continue
        if math["min_profit"] > 0:
            results.append(
                {
                    "market_id": row.market_id,
                    "outcome": row.outcome,
                    "back_odds": str(row.back_odds),
                    "lay_odds": str(row.lay_odds),
                    "back_bookmaker": row.back_bookmaker,
                    "lay_bookmaker": row.lay_bookmaker,
                    "lay_stake_per_back_1": str(math["lay_stake"]),
                    "profit_if_win": str(math["profit_win"]),
                    "profit_if_lose": str(math["profit_lose"]),
                }
            )
    return results


def find_back_lay_arbs_cross_event(
    session: Session, commission_rate: Decimal, allow_same_bookmaker: bool = False
) -> list[dict]:
    back_rows = _latest_side_rows(session, "back")
    lay_rows = _latest_side_rows(session, "lay")

    def key(row: dict) -> tuple:
        return (
            _normalize_team(row["home"]),
            _normalize_team(row["away"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            _time_bucket(row["start_time"], minutes=24 * 60),
        )

    def key_no_time(row: dict) -> tuple:
        return (
            _normalize_team(row["home"]),
            _normalize_team(row["away"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            None,
        )

    def key_swapped(row: dict) -> tuple:
        return (
            _normalize_team(row["away"]),
            _normalize_team(row["home"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            _time_bucket(row["start_time"], minutes=24 * 60),
        )

    def key_swapped_no_time(row: dict) -> tuple:
        return (
            _normalize_team(row["away"]),
            _normalize_team(row["home"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            None,
        )

    back_by_key: dict[tuple, dict[str, list[dict]]] = {}
    lay_by_key: dict[tuple, dict[str, list[dict]]] = {}

    for row in back_rows:
        k = key(row)
        back_by_key.setdefault(k, {}).setdefault(row["outcome"], []).append(row)
        kn = key_no_time(row)
        back_by_key.setdefault(kn, {}).setdefault(row["outcome"], []).append(row)

    for row in lay_rows:
        k = key(row)
        lay_by_key.setdefault(k, {}).setdefault(row["outcome"], []).append(row)
        ks = key_swapped(row)
        lay_by_key.setdefault(ks, {}).setdefault(row["outcome"], []).append(row)
        kn = key_no_time(row)
        lay_by_key.setdefault(kn, {}).setdefault(row["outcome"], []).append(row)
        ksn = key_swapped_no_time(row)
        lay_by_key.setdefault(ksn, {}).setdefault(row["outcome"], []).append(row)

    results = []
    for k in back_by_key.keys() & lay_by_key.keys():
        back_outcomes = back_by_key[k]
        lay_outcomes = lay_by_key[k]
        for outcome, backs in back_outcomes.items():
            lays = lay_outcomes.get(outcome, [])
            if not backs or not lays:
                continue
            backs_sorted = sorted(backs, key=lambda r: r["odds"], reverse=True)
            lays_sorted = sorted(lays, key=lambda r: r["odds"])

            best = None
            for back in backs_sorted:
                for lay in lays_sorted:
                    if not allow_same_bookmaker and back["bookmaker_id"] == lay["bookmaker_id"]:
                        continue
                    math = _back_lay_math(back["odds"], lay["odds"], commission_rate)
                    if not math:
                        continue
                    if math["min_profit"] > 0:
                        best = (back, lay, math)
                        break
                if best:
                    break
            if not best:
                continue
            back, lay, math = best
            results.append(
                {
                    "event": f'{back["home"]} vs {back["away"]}',
                    "market_type": back["market_type"],
                    "spec": back["spec"],
                    "event_start_time": (
                        back["start_time"].isoformat()
                        if back.get("start_time")
                        else ""
                    ),
                    "outcome": back["outcome"],
                    "back_odds": str(back["odds"]),
                    "lay_odds": str(lay["odds"]),
                    "back_bookmaker": back["bookmaker"],
                    "lay_bookmaker": lay["bookmaker"],
                    "lay_stake_per_back_1": str(math["lay_stake"]),
                    "profit_if_win": str(math["profit_win"]),
                    "profit_if_lose": str(math["profit_lose"]),
                }
            )
    return results


def debug_back_lay_matches(session: Session) -> list[dict]:
    back_rows = _latest_side_rows(session, "back")
    lay_rows = _latest_side_rows(session, "lay")

    def key(row: dict) -> tuple:
        return (
            _normalize_team(row["home"]),
            _normalize_team(row["away"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            _time_bucket(row["start_time"], minutes=24 * 60),
        )

    def key_no_time(row: dict) -> tuple:
        return (
            _normalize_team(row["home"]),
            _normalize_team(row["away"]),
            (row["market_type"] or "").strip().upper(),
            _normalize_spec(row["market_type"], row["spec"]),
            None,
        )

    back_by_key: dict[tuple, dict[str, list[dict]]] = {}
    lay_by_key: dict[tuple, dict[str, list[dict]]] = {}

    for row in back_rows:
        k = key(row)
        back_by_key.setdefault(k, {}).setdefault(row["outcome"], []).append(row)
        kn = key_no_time(row)
        back_by_key.setdefault(kn, {}).setdefault(row["outcome"], []).append(row)

    for row in lay_rows:
        k = key(row)
        lay_by_key.setdefault(k, {}).setdefault(row["outcome"], []).append(row)
        kn = key_no_time(row)
        lay_by_key.setdefault(kn, {}).setdefault(row["outcome"], []).append(row)

    results = []
    for k in back_by_key.keys() & lay_by_key.keys():
        home, away, market_type, spec, bucket = k
        for outcome, backs in back_by_key[k].items():
            lays = lay_by_key[k].get(outcome, [])
            if not backs or not lays:
                continue
            backs_best = {}
            for row in backs:
                current = backs_best.get(row["bookmaker"])
                if current is None or row["odds"] > current["odds"]:
                    backs_best[row["bookmaker"]] = row
            lays_best = {}
            for row in lays:
                current = lays_best.get(row["bookmaker"])
                if current is None or row["odds"] < current["odds"]:
                    lays_best[row["bookmaker"]] = row
            backs_sorted = sorted(backs_best.values(), key=lambda r: r["odds"], reverse=True)
            lays_sorted = sorted(lays_best.values(), key=lambda r: r["odds"])
            best_back = backs_sorted[0]
            best_lay = lays_sorted[0]
            results.append(
                {
                    "event": f'{best_back["home"]} vs {best_back["away"]}',
                    "market_type": market_type,
                    "spec": spec,
                    "outcome": outcome,
                    "back": {
                        "bookmaker": best_back["bookmaker"],
                        "odds": str(best_back["odds"]),
                    },
                    "lay": {
                        "bookmaker": best_lay["bookmaker"],
                        "odds": str(best_lay["odds"]),
                    },
                    "backs_all": [
                        {"bookmaker": row["bookmaker"], "odds": str(row["odds"])}
                        for row in backs_sorted[:5]
                    ],
                    "lays_all": [
                        {"bookmaker": row["bookmaker"], "odds": str(row["odds"])}
                        for row in lays_sorted[:5]
                    ],
                    "time_bucket": bucket,
                }
            )
    return results


def debug_event_keys(session: Session, limit_per_bookmaker: int = 50) -> list[dict]:
    rows = _latest_side_rows(session, "back")
    per_bookmaker: dict[str, dict[str, dict]] = {}

    for row in rows:
        bookmaker = row["bookmaker"]
        home_norm = _normalize_team(row["home"])
        away_norm = _normalize_team(row["away"])
        bucket = _time_bucket(row["start_time"])
        market_type = (row["market_type"] or "").strip().upper()
        spec_norm = _normalize_spec(row["market_type"], row["spec"])
        bucket = _time_bucket(row["start_time"], minutes=24 * 60)
        key = (home_norm, away_norm, market_type, spec_norm, bucket)
        key_no_time = (home_norm, away_norm, market_type, spec_norm, None)

        store = per_bookmaker.setdefault(bookmaker, {})
        if len(store) >= limit_per_bookmaker:
            continue
        if str(key) in store:
            continue
        store[str(key)] = {
            "event": f'{row["home"]} vs {row["away"]}',
            "market_type": row["market_type"],
            "market_type_norm": market_type,
            "spec": row["spec"],
            "spec_norm": spec_norm,
            "home_norm": home_norm,
            "away_norm": away_norm,
            "start_time": row["start_time"],
            "time_bucket": bucket,
            "key": key,
            "key_no_time": key_no_time,
        }

    results = []
    for bookmaker, keys in sorted(per_bookmaker.items()):
        results.append(
            {
                "bookmaker": bookmaker,
                "count": len(keys),
            "samples": list(keys.values()),
        }
    )
    return results
