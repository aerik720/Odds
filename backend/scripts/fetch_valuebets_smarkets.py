import argparse
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
import time

import requests

V3_API_BASE = "https://api.odds-api.io/v3"
V4_API_BASE = "https://api.the-odds-api.com/v4"
SESSION = requests.Session()
SESSION.trust_env = False
ROOT_DIR = Path(__file__).resolve().parents[2]

SOCCER_LEAGUE_MAP: dict[str, str] = {}
SOCCER_LEAGUE_NAME_MAP: dict[str, str] = {}
SOCCER_LEAGUE_NAME_SORTED: list[tuple[str, str]] = []

MARKET_MAP = {
    "match result": "h2h",
    "full time result": "h2h",
    "full-time result": "h2h",
    "1x2": "h2h",
    "match winner": "h2h",
    "moneyline": "h2h",
    "ml": "h2h",
    "both teams to score": "btts",
    "btts": "btts",
}


def _load_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, val = line.partition("=")
        if sep != "=":
            continue
        if key.strip() == name:
            return val.strip().strip('"')
    return None


def _get_json(url: str, params: dict) -> list | dict:
    resp = SESSION.get(url, params=params, timeout=30)
    if not resp.ok:
        message = resp.text.strip()
        raise RuntimeError(f"Odds API error {resp.status_code}: {message}")
    return resp.json()


def _put(path: str, params: dict) -> dict:
    resp = SESSION.put(f"{V3_API_BASE}{path}", params=params, timeout=30)
    if not resp.ok:
        message = resp.text.strip()
        raise RuntimeError(f"Odds API error {resp.status_code}: {message}")
    return resp.json() if resp.text.strip() else {}


def _normalize_team(value: str) -> str:
    base = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in base if ch.isalnum() or ch.isspace()).lower()
    return " ".join(stripped.split())


def _normalize_slug(value: str) -> str:
    return "-".join(value.lower().replace("_", "-").split())


def _normalize_title(value: str) -> str:
    base = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in base if ch.isalnum() or ch.isspace()).lower()
    return " ".join(stripped.split())


def _normalize_sport_name(value: str) -> str:
    sport = (value or "").strip().lower()
    if sport in {"football", "soccer"}:
        return "soccer"
    return sport


def _build_soccer_league_map() -> None:
    if SOCCER_LEAGUE_MAP:
        return
    sports_path = ROOT_DIR / "docs" / "smarketsports.json"
    if not sports_path.exists():
        return
    try:
        sports = json.loads(sports_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    for sport in sports or []:
        key = sport.get("key") or ""
        if not key.startswith("soccer_"):
            continue
        slug_base = _normalize_slug(key.replace("soccer_", "", 1))
        candidates = {slug_base}
        if slug_base == "epl":
            candidates.add("england-premier-league")
        if slug_base == "efl-champ":
            candidates.add("england-championship")
        if slug_base.startswith("uefa-"):
            candidates.add(f"international-clubs-{slug_base}")
        if slug_base.startswith("conmebol-"):
            candidates.add(f"international-clubs-{slug_base}")
        if slug_base.endswith("la-liga"):
            candidates.add(slug_base.replace("la-liga", "laliga"))
        if "champions-league" in slug_base:
            candidates.add(slug_base.replace("champions-league", "champs-league"))
            candidates.add(f"international-clubs-{slug_base}")
        if "europa-league" in slug_base:
            candidates.add(f"international-clubs-{slug_base}")
        for candidate in candidates:
            if candidate not in SOCCER_LEAGUE_MAP:
                SOCCER_LEAGUE_MAP[candidate] = key
        title = sport.get("title") or ""
        if title:
            normalized_title = _normalize_title(title)
            if normalized_title not in SOCCER_LEAGUE_NAME_MAP:
                SOCCER_LEAGUE_NAME_MAP[normalized_title] = key
        description = sport.get("description") or ""
        if description:
            normalized_desc = _normalize_title(description)
            if normalized_desc and normalized_desc not in SOCCER_LEAGUE_NAME_MAP:
                SOCCER_LEAGUE_NAME_MAP[normalized_desc] = key

    # Manual aliases for common Odds API league name formats.
    aliases = {
        "england premier league": "soccer_epl",
        "england championship": "soccer_efl_champ",
        "england league one": "soccer_england_league1",
        "england league two": "soccer_england_league2",
        "england efl cup": "soccer_england_efl_cup",
        "spain laliga": "soccer_spain_la_liga",
        "spain la liga": "soccer_spain_la_liga",
        "italy serie a": "soccer_italy_serie_a",
        "france ligue 1": "soccer_france_ligue_one",
        "germany bundesliga": "soccer_germany_bundesliga",
        "greece super league": "soccer_greece_super_league",
        "international clubs uefa champions league": "soccer_uefa_champs_league",
        "international clubs uefa europa league": "soccer_uefa_europa_league",
    }
    for label, key in aliases.items():
        normalized = _normalize_title(label)
        if normalized not in SOCCER_LEAGUE_NAME_MAP:
            SOCCER_LEAGUE_NAME_MAP[normalized] = key

    global SOCCER_LEAGUE_NAME_SORTED
    SOCCER_LEAGUE_NAME_SORTED = sorted(
        SOCCER_LEAGUE_NAME_MAP.items(), key=lambda x: len(x[0]), reverse=True
    )


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _choose_sport_key(event: dict) -> str | None:
    _build_soccer_league_map()
    sport = _normalize_sport_name(event.get("sport"))
    if sport != "soccer":
        return None
    league = event.get("league")
    if isinstance(league, dict):
        league = league.get("slug") or league.get("name") or ""
    league_text = str(league or "").strip()
    if not league_text:
        return None
    slug = _normalize_slug(league_text)
    if slug in SOCCER_LEAGUE_MAP:
        return SOCCER_LEAGUE_MAP[slug]
    title_key = _normalize_title(league_text)
    direct = SOCCER_LEAGUE_NAME_MAP.get(title_key)
    if direct:
        return direct
    # Fuzzy match by containment of known titles/descriptions.
    for title, key in SOCCER_LEAGUE_NAME_SORTED:
        if not title:
            continue
        if title in title_key:
            return key
    return None


def _match_event(
    target: dict, candidates: list[dict], max_hours: int = 6
) -> dict | None:
    home = _normalize_team(target.get("home") or "")
    away = _normalize_team(target.get("away") or "")
    target_time = _parse_time(target.get("date"))
    best = None
    best_delta = None
    for candidate in candidates:
        cand_home = _normalize_team(candidate.get("home_team") or "")
        cand_away = _normalize_team(candidate.get("away_team") or "")
        if {home, away} != {cand_home, cand_away}:
            continue
        cand_time = _parse_time(candidate.get("commence_time"))
        if target_time and cand_time:
            delta = abs((cand_time - target_time).total_seconds())
            if delta > max_hours * 3600:
                continue
        else:
            delta = 0
        if best is None or delta < (best_delta or 0):
            best = candidate
            best_delta = delta
    return best


def _pick_market(markets: list[dict], key: str) -> dict | None:
    for market in markets or []:
        if market.get("key") == key:
            return market
    return None


def _resolve_outcome(
    market_key: str,
    outcomes: list[dict],
    bet_side: str,
    home_team: str,
    away_team: str,
) -> dict | None:
    side = (bet_side or "").lower()
    if market_key == "h2h":
        if side == "home":
            name = home_team
        elif side == "away":
            name = away_team
        elif side == "draw":
            name = "Draw"
        else:
            name = bet_side
    elif market_key == "btts":
        if side in {"yes", "no"}:
            name = side.capitalize()
        else:
            name = bet_side
    else:
        name = bet_side
    for outcome in outcomes or []:
        if (outcome.get("name") or "").strip().lower() == (name or "").strip().lower():
            return outcome
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bookmaker",
        default="",
        help="Value-bet bookmaker name (v3).",
    )
    parser.add_argument(
        "--auto-reset-bookmakers",
        action="store_true",
        default=_load_env_value("ODDS_API_AUTO_RESET_BOOKMAKERS") == "1",
        help="Auto clear/select bookmakers if free-plan limit blocks value-bets.",
    )
    parser.add_argument(
        "--sports",
        default="football",
        help="Comma-separated sports to include (default: football).",
    )
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="Include unmatched/unsupported items in output.",
    )
    parser.add_argument(
        "--debug-leagues",
        type=int,
        default=0,
        help="Print up to N unique unsupported league values.",
    )
    parser.add_argument(
        "--debug-samples",
        type=int,
        default=0,
        help="Print up to N sample records for filtered/unmatched items.",
    )
    parser.add_argument(
        "--valuebets-only",
        action="store_true",
        help="Only fetch value bets and write output without Smarkets matching.",
    )
    parser.add_argument(
        "--max-sports",
        type=int,
        default=8,
        help="Max number of v4 sport keys to fetch per run.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=1.2,
        help="Min delay (seconds) between v4 requests.",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT_DIR / "backend" / "data" / "valuebets_smarkets.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--regions",
        default="uk",
        help="V4 regions for smarkets (default: uk).",
    )
    parser.add_argument(
        "--max-hours",
        type=int,
        default=6,
        help="Max hours diff when matching events.",
    )
    args = parser.parse_args()

    v3_key = _load_env_value("ODDS_API_KEY")
    v4_key = _load_env_value("SMARKETS_ODDS_API_KEY") or _load_env_value(
        "SMARKET_ODDS_API_KEY"
    )
    if not v3_key:
        raise RuntimeError("Missing ODDS_API_KEY in environment.")
    if not v4_key:
        raise RuntimeError("Missing SMARKETS_ODDS_API_KEY in environment.")

    requested_bookmaker = args.bookmaker.strip()
    if not requested_bookmaker:
        requested_bookmaker = (
            _load_env_value("ODDS_API_VALUEBET_BOOKMAKER")
            or (_load_env_value("ODDS_API_BOOKMAKERS") or "").split(",")[0].strip()
            or "Bet365"
        )
    print(f"Using value-bet bookmaker: {requested_bookmaker}")

    sports_filter = {
        _normalize_sport_name(s) for s in (args.sports or "").split(",") if s.strip()
    }

    try:
        valuebets = _get_json(
            f"{V3_API_BASE}/value-bets",
            {
                "apiKey": v3_key,
                "bookmaker": requested_bookmaker,
                "includeEventDetails": "true",
            },
        )
    except RuntimeError as exc:
        message = str(exc)
        if (
            args.auto_reset_bookmakers
            and "allowed max 2 bookmakers" in message.lower()
        ):
            print("Free-plan bookmaker limit hit. Resetting selected bookmakers...")
            _put("/bookmakers/selected/clear", {"apiKey": v3_key})
            _put(
                "/bookmakers/selected/select",
                {"apiKey": v3_key, "bookmakers": requested_bookmaker},
            )
            valuebets = _get_json(
                f"{V3_API_BASE}/value-bets",
                {
                    "apiKey": v3_key,
                    "bookmaker": requested_bookmaker,
                    "includeEventDetails": "true",
                },
            )
        else:
            raise

    if args.valuebets_only:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output = [
            {
                "valuebet": bet,
                "smarkets": None,
                "match_status": "valuebet",
                "smarkets_event": None,
            }
            for bet in (valuebets or [])
        ]
        output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        print(f"Wrote {len(output)} records to {output_path}.")
        return

    events_by_sport: dict[str, list[dict]] = {}
    total_bets = len(valuebets or [])
    skipped_sport = 0
    skipped_unsupported = 0
    unsupported_leagues: dict[str, int] = {}
    for bet in valuebets or []:
        event = bet.get("event") or {}
        sport_name = _normalize_sport_name(event.get("sport"))
        if sports_filter and sport_name not in sports_filter:
            if args.include_unsupported:
                bet["_skip_reason"] = "filtered sport"
            else:
                skipped_sport += 1
                continue
        sport_key = _choose_sport_key(event)
        if not sport_key:
            if args.include_unsupported:
                bet["_skip_reason"] = "unsupported sport/league"
            else:
                skipped_unsupported += 1
                if args.debug_leagues:
                    league = event.get("league")
                    if isinstance(league, dict):
                        league = league.get("slug") or league.get("name") or ""
                    league_text = str(league or "").strip() or "(empty)"
                    unsupported_leagues[league_text] = unsupported_leagues.get(league_text, 0) + 1
                continue
        events_by_sport.setdefault(sport_key, []).append(bet)

    print(
        "Value bets:",
        f"total={total_bets}",
        f"kept={sum(len(items) for items in events_by_sport.values())}",
        f"filtered_sport={skipped_sport}",
        f"unsupported={skipped_unsupported}",
    )
    if args.debug_leagues and unsupported_leagues:
        print("Unsupported leagues (sample):")
        for league, count in sorted(unsupported_leagues.items(), key=lambda x: -x[1])[
            : args.debug_leagues
        ]:
            print(f"- {league}: {count}")

    v4_cache: dict[str, list[dict]] = {}
    fetched_sports = 0
    for sport_key in events_by_sport:
        if fetched_sports >= args.max_sports:
            print("Reached max sports limit, skipping remaining v4 requests.")
            break
        base_params = {
            "apiKey": v4_key,
            "regions": args.regions,
            "bookmakers": "smarkets",
            "oddsFormat": "decimal",
        }
        if fetched_sports:
            time.sleep(args.min_delay)
        try:
            v4_cache[sport_key] = _get_json(
                f"{V4_API_BASE}/sports/{sport_key}/odds",
                {**base_params, "markets": "h2h,btts"},
            )
            fetched_sports += 1
        except RuntimeError as exc:
            message = str(exc)
            if "UNKNOWN_SPORT" in message or "Unknown sport" in message:
                print(f"Skipping unknown v4 sport key: {sport_key}")
                continue
            if "INVALID_MARKET" in message or "Markets not supported" in message:
                print(f"Market btts not supported for {sport_key}, retrying with h2h only.")
                time.sleep(args.min_delay)
                v4_cache[sport_key] = _get_json(
                    f"{V4_API_BASE}/sports/{sport_key}/odds",
                    {**base_params, "markets": "h2h"},
                )
                fetched_sports += 1
                continue
            if "EXCEEDED_FREQ_LIMIT" in message or "too frequent" in message.lower():
                print("Hit v4 frequency limit, stopping v4 requests early.")
                break
            raise

    output = []
    unmatched = 0
    matched_count = 0
    status_counts: dict[str, int] = {}
    debug_samples: list[str] = []
    debug_limit = max(args.debug_samples or 0, args.debug_leagues or 0)
    for bet in valuebets or []:
        event = bet.get("event") or {}
        sport_key = _choose_sport_key(event)
        market = bet.get("market") or {}
        market_name = (market.get("name") or "").lower()
        market_key = MARKET_MAP.get(market_name)
        value_price = (
            bet.get("odds")
            or bet.get("price")
            or bet.get("decimalOdds")
            or bet.get("oddsDecimal")
        )

        record = {
            "valuebet": bet,
            "smarkets": None,
            "match_status": "unmatched",
            "smarkets_event": None,
        }

        if not sport_key:
            record["match_status"] = "unsupported sport/league"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            if args.include_unsupported:
                unmatched += 1
                output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                league = event.get("league")
                if isinstance(league, dict):
                    league = league.get("name") or league.get("slug") or ""
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | league={league} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=unsupported sport/league"
                )
            continue
        if not market_key:
            record["match_status"] = "unsupported market"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            if args.include_unsupported:
                unmatched += 1
                output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=unsupported market"
                )
            continue

        candidates = v4_cache.get(sport_key, [])
        matched_event = _match_event(event, candidates, max_hours=args.max_hours)
        if not matched_event:
            record["match_status"] = "no smarkets event match"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            if args.include_unsupported:
                unmatched += 1
                output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=no smarkets event match"
                )
            continue

        record["smarkets_event"] = {
            "id": matched_event.get("id"),
            "home_team": matched_event.get("home_team"),
            "away_team": matched_event.get("away_team"),
            "commence_time": matched_event.get("commence_time"),
        }

        smarkets = None
        for bookmaker in matched_event.get("bookmakers", []) or []:
            if bookmaker.get("key") == "smarkets":
                smarkets = bookmaker
                break
        if not smarkets:
            record["match_status"] = "smarkets bookmaker missing"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            if args.include_unsupported:
                unmatched += 1
                output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=smarkets bookmaker missing"
                )
            continue

        market_data = _pick_market(smarkets.get("markets") or [], market_key)
        if not market_data:
            record["match_status"] = "smarkets market missing"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            if args.include_unsupported:
                unmatched += 1
                output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=smarkets market missing"
                )
            continue

        bet_side = bet.get("betSide") or ""
        outcome = _resolve_outcome(
            market_key,
            market_data.get("outcomes") or [],
            bet_side,
            matched_event.get("home_team") or "",
            matched_event.get("away_team") or "",
        )
        if not outcome:
            record["match_status"] = "smarkets odds N/A"
            status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
            unmatched += 1
            output.append(record)
            if debug_limit and len(debug_samples) < debug_limit:
                debug_samples.append(
                    f"{event.get('home')} vs {event.get('away')} | market={market_name} | "
                    f"side={bet.get('betSide')} | value_odds={value_price or 'N/A'} | status=smarkets odds N/A"
                )
            continue

        record["smarkets"] = {
            "bookmaker": "smarkets",
            "market": market_key,
            "outcome": outcome.get("name"),
            "price": outcome.get("price"),
        }
        record["match_status"] = "matched"
        status_counts[record["match_status"]] = status_counts.get(record["match_status"], 0) + 1
        matched_count += 1
        output.append(record)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"Wrote {len(output)} records to {output_path}.")
    print(f"Match summary: matched={matched_count} unmatched={unmatched}")
    if status_counts:
        print("Match status counts:")
        for key, value in sorted(status_counts.items(), key=lambda x: -x[1]):
            print(f"- {key}: {value}")
    if debug_samples:
        print("Sample records:")
        for line in debug_samples:
            print(f"- {line}")


if __name__ == "__main__":
    main()
