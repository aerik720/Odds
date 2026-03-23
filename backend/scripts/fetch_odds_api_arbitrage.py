import argparse
import json
import os
import smtplib
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path

import requests

API_BASE = "https://api.odds-api.io/v3"
SESSION = requests.Session()
SESSION.trust_env = False
ROOT_DIR = Path(__file__).resolve().parents[2]

MARKET_ALIASES = {
    "ml": "matchresult",
    "moneyline": "matchresult",
    "matchwinner": "matchresult",
    "matchresult": "matchresult",
    "fulltimeresult": "matchresult",
    "1x2": "matchresult",
    "totals": "totals",
    "total": "totals",
    "spread": "spread",
    "handicap": "spread",
    "btts": "bothteamstoscore",
    "bothteamstoscore": "bothteamstoscore",
}


def _normalize_name(name: str) -> str:
    return "".join(ch.lower() for ch in name if ch.isalnum())


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


def _get(path: str, params: dict) -> list[dict]:
    resp = SESSION.get(f"{API_BASE}{path}", params=params, timeout=30)
    if not resp.ok:
        message = resp.text.strip()
        raise RuntimeError(f"Odds API error {resp.status_code}: {message}")
    return resp.json()


def _get_bookmakers() -> list[str]:
    resp = SESSION.get(f"{API_BASE}/bookmakers", timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    return [item.get("name", "") for item in payload if item.get("name")]


def _get_env(name: str, default: str | None = None) -> str | None:
    value = _load_env_value(name)
    if value:
        return value
    return default


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _send_email(subject: str, body: str) -> None:
    host = _get_env("SMTP_HOST")
    port = int(_get_env("SMTP_PORT", "587") or "587")
    user = _get_env("SMTP_USER")
    password = _get_env("SMTP_PASSWORD")
    sender = _get_env("SMTP_FROM", user or "")
    recipients = _get_env("SMTP_TO")
    use_tls = _parse_bool(_get_env("SMTP_USE_TLS"), True)

    if not host or not sender or not recipients:
        print("SMTP config missing. Skipping email notification.")
        return

    to_list = [addr.strip() for addr in recipients.split(",") if addr.strip()]
    if not to_list:
        print("SMTP_TO is empty. Skipping email notification.")
        return

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(to_list)
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as server:
        if use_tls:
            server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(message)


def _summarize_items(items: list[dict]) -> str:
    lines = []
    for item in items:
        event = item.get("event") or {}
        event_name = item.get("event_name")
        if not event_name and event.get("home") and event.get("away"):
            event_name = f"{event.get('home')} vs {event.get('away')}"
        market = item.get("market") or {}
        market_label = market.get("name", "Market")
        if market.get("hdp") is not None:
            market_label = f"{market_label} {market.get('hdp')}"
        margin = item.get("profitMargin")
        lines.append(f"- {event_name or 'Unknown event'} | {market_label} | {margin}%")
    return "\n".join(lines)

def _parse_decimal(value: str | int | float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _odds_equal(a: str | int | float | None, b: str | int | float | None) -> bool:
    da = _parse_decimal(a)
    db = _parse_decimal(b)
    if da is None or db is None:
        return False
    return abs(da - db) <= Decimal("0.0001")


def _normalize_market(name: str) -> str:
    base = _normalize_name(name)
    return MARKET_ALIASES.get(base, base)


def _hdp_matches(hdp_value: str | int | float | None, target: str | int | float | None) -> bool:
    if target is None:
        return True
    dv = _parse_decimal(hdp_value)
    dt = _parse_decimal(target)
    if dv is None or dt is None:
        return False
    return abs(dv - dt) <= Decimal("0.0001")


def _leg_matches_market(
    markets: list[dict], market_name: str, hdp: str | int | float | None, side: str, expected: str
) -> bool:
    normalized_target = _normalize_market(market_name)
    for market in markets or []:
        if _normalize_market(market.get("name", "")) != normalized_target:
            continue
        for odds in market.get("odds", []) or []:
            if not _hdp_matches(odds.get("hdp"), hdp):
                continue
            if _odds_equal(odds.get(side), expected):
                return True
    return False


def _find_current_odds(
    markets: list[dict], market_name: str, hdp: str | int | float | None, side: str
) -> str | None:
    normalized_target = _normalize_market(market_name)
    for market in markets or []:
        if _normalize_market(market.get("name", "")) != normalized_target:
            continue
        for odds in market.get("odds", []) or []:
            if not _hdp_matches(odds.get("hdp"), hdp):
                continue
            value = odds.get(side)
            if value is not None:
                return str(value)
    return None


def _verify_arbitrage_items(
    api_key: str, items: list[dict], max_checks: int = 20
) -> tuple[list[dict], int, int]:
    if not items:
        return [], 0, 0
    cache: dict[int, dict] = {}
    verified: list[dict] = []
    checked = 0
    filtered = 0

    for item in items:
        event_id = item.get("eventId")
        if event_id is None:
            verified.append(item)
            continue
        if checked >= max_checks:
            verified.append(item)
            continue
        checked += 1
        if event_id not in cache:
            bookmakers = ",".join(
                [leg.get("bookmaker") for leg in item.get("legs", []) if leg.get("bookmaker")]
            )
            cache[event_id] = _get(
                "/odds",
                {
                    "apiKey": api_key,
                    "eventId": str(event_id),
                    "bookmakers": bookmakers,
                },
            )
        odds_payload = cache.get(event_id) or {}
        markets_by_bookmaker = odds_payload.get("bookmakers", {}) or {}
        market = item.get("market") or {}
        market_name = market.get("name", "")
        hdp = market.get("hdp")
        legs = item.get("legs") or []
        if not market_name or not legs:
            verified.append(item)
            continue

        all_ok = True
        current_odds: list[Decimal] = []
        for leg in legs:
            bookmaker = leg.get("bookmaker")
            side = leg.get("side")
            odds = leg.get("odds")
            if not bookmaker or not side or odds is None:
                all_ok = False
                break
            book_markets = markets_by_bookmaker.get(bookmaker) or []
            if not _leg_matches_market(book_markets, market_name, hdp, side, odds):
                all_ok = False
                current = _find_current_odds(book_markets, market_name, hdp, side)
                if current is None:
                    # If we can't find current odds, keep the item to avoid over-filtering.
                    all_ok = True
                    current_dec = _parse_decimal(odds)
                    if current_dec is not None:
                        current_odds.append(current_dec)
                    print(
                        "Odds N/A during check:",
                        item.get("id"),
                        "|",
                        bookmaker,
                        side,
                        odds,
                    )
                    continue
                current_dec = _parse_decimal(current) if current else None
                if current_dec is not None:
                    current_odds.append(current_dec)
            else:
                current_dec = _parse_decimal(odds)
                current_odds.append(current_dec or Decimal("0"))
        if all_ok:
            verified.append(item)
        else:
            if all(current > 0 for current in current_odds):
                implied = sum(Decimal("1") / odd for odd in current_odds)
                if implied < Decimal("1"):
                    # Still an arbitrage at current odds. Update item to current values.
                    for leg in legs:
                        bookmaker = leg.get("bookmaker")
                        side = leg.get("side")
                        if bookmaker and side:
                            current = _find_current_odds(
                                markets_by_bookmaker.get(bookmaker) or [],
                                market_name,
                                hdp,
                                side,
                            )
                            if current is not None:
                                leg["odds"] = str(current)
                    item["impliedProbability"] = float(implied)
                    item["profitMargin"] = float((Decimal("1") - implied) * 100)
                    item["updatedAt"] = datetime.now(timezone.utc).isoformat()
                    verified.append(item)
                    print(
                        "Arbitrage still valid with updated odds:",
                        item.get("id"),
                        "implied",
                        f"{float(implied):.4f}",
                    )
                    continue
            filtered += 1
            event_info = item.get("event") or {}
            event_name = item.get("event_name")
            if not event_name and event_info.get("home") and event_info.get("away"):
                event_name = f"{event_info.get('home')} vs {event_info.get('away')}"
            market_label = market_name
            if hdp is not None:
                market_label = f"{market_label} {hdp}"
            legs_desc = []
            for leg in legs:
                bookmaker = leg.get("bookmaker")
                side = leg.get("side")
                expected = leg.get("odds")
                current = None
                if bookmaker:
                    current = _find_current_odds(
                        markets_by_bookmaker.get(bookmaker) or [],
                        market_name,
                        hdp,
                        side,
                    )
                if current:
                    legs_desc.append(
                        f"{bookmaker} {side} {expected} (now {current})"
                    )
                else:
                    legs_desc.append(f"{bookmaker} {side} {expected} (now n/a)")
            print(
                "Filtered stale arbitrage:",
                item.get("id"),
                "|",
                event_name or "Unknown event",
                "|",
                market_label or "Unknown market",
                "| legs:",
                "; ".join(legs_desc),
            )
    return verified, filtered, checked


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bookmakers",
        default=_load_env_value("ODDS_API_BOOKMAKERS") or "",
        help="Comma-separated bookmaker names.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max results (default 50).",
    )
    parser.add_argument(
        "--output",
        default=str(ROOT_DIR / "backend" / "data" / "odds_api_arbitrage.json"),
        help="Output JSON path.",
    )
    parser.add_argument(
        "--include-events",
        action="store_true",
        default=True,
        help="Include event details in response.",
    )
    args = parser.parse_args()

    api_key = _load_env_value("ODDS_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ODDS_API_KEY in environment.")

    requested = [b.strip() for b in args.bookmakers.split(",") if b.strip()]
    if not requested:
        raise RuntimeError("Missing bookmakers list. Set ODDS_API_BOOKMAKERS or --bookmakers.")

    available = _get_bookmakers()
    available_map = {_normalize_name(name): name for name in available}
    resolved = []
    missing = []
    for name in requested:
        key = _normalize_name(name)
        match = available_map.get(key)
        if match:
            resolved.append(match)
        else:
            missing.append(name)
    if missing:
        print(f"Unknown bookmakers skipped: {', '.join(missing)}")
    if not resolved:
        raise RuntimeError(
            "No valid bookmakers after lookup. Check /bookmakers for supported names."
        )

    payload = _get(
        "/arbitrage-bets",
        {
            "apiKey": api_key,
            "bookmakers": ",".join(resolved),
            "limit": args.limit,
            "includeEventDetails": str(args.include_events).lower(),
        },
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    previous = []
    if output_path.exists():
        try:
            previous = json.loads(output_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            previous = []
    prev_ids = {item.get("id") for item in previous if item.get("id")}
    new_items = [item for item in payload if item.get("id") not in prev_ids]
    if new_items:
        verified_new, filtered_count, checked_count = _verify_arbitrage_items(
            api_key, new_items
        )
        verified_ids = {item.get("id") for item in verified_new if item.get("id")}
        payload = [
            item
            for item in payload
            if item.get("id") in verified_ids or item.get("id") in prev_ids
        ]
        new_items = [item for item in verified_new if item.get("id") in verified_ids]
        print(
            "Verification:",
            f"checked={checked_count}",
            f"filtered={filtered_count}",
            f"kept_new={len(new_items)}",
        )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(payload)} arbitrage opportunities to {output_path}.")

    if new_items:
        subject = f"New arbitrage opportunities ({len(new_items)})"
        body = "New arbitrage opportunities detected:\n\n"
        body += _summarize_items(new_items)
        _send_email(subject, body)


if __name__ == "__main__":
    main()
