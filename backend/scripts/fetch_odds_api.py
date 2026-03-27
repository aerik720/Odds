import argparse
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Iterable

import requests

API_BASE = "https://api.odds-api.io/v3"


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


def _internal_api_base() -> str:
    env_base = os.getenv("API_BASE_URL")
    if env_base:
        return env_base.rstrip("/")
    port = os.getenv("PORT")
    if port:
        return f"http://127.0.0.1:{port}"
    return "http://127.0.0.1:8000"
API_KEY = _load_env_value("ODDS_API_KEY")
BOOKMAKER_REGION_DEFAULT = "API"
SESSION = requests.Session()
SESSION.trust_env = False
ADMIN_EMAIL = _load_env_value("ADMIN_EMAIL")
ADMIN_PASSWORD = _load_env_value("ADMIN_PASSWORD")
ADMIN_TOKEN: str | None = None

DEFAULT_FOOTBALL_LEAGUES = [
    "england-premier-league",
    "england-championship",
    "spain-laliga",
    "international-clubs-uefa-europa-league",
    "germany-bundesliga",
    "italy-serie-a",
]

LEAGUE_ALIASES = {
    "england-the-championship": "england-championship",
    "spain-la-liga": "spain-laliga",
    "uefa-europa-league": "international-clubs-uefa-europa-league",
}


def _get(path: str, params: dict) -> dict | list:
    resp = SESSION.get(
        f"{API_BASE}{path}",
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def _post(path: str, payload: dict) -> dict:
    headers = {}
    if ADMIN_TOKEN:
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
    resp = requests.post(
        f"{_internal_api_base()}{path}", json=payload, headers=headers, timeout=30
    )
    resp.raise_for_status()
    return resp.json()


def _get_admin_token() -> str | None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return None
    resp = requests.post(
        f"{_internal_api_base()}/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("access_token")


def _normalize_bookmaker(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _resolve_bookmakers(requested: list[str]) -> list[str]:
    data = _get("/bookmakers", {"apiKey": API_KEY})
    supported = [row.get("name", "") for row in data or [] if row.get("name")]
    norm_map = {}
    for name in supported:
        norm = _normalize_bookmaker(name)
        if norm and norm not in norm_map:
            norm_map[norm] = name

    resolved = []
    for name in requested:
        norm = _normalize_bookmaker(name)
        if norm in norm_map:
            resolved.append(norm_map[norm])
            continue
        match = next((n for n in supported if norm in _normalize_bookmaker(n)), "")
        if match:
            resolved.append(match)
            continue
        print(f"Bookmaker not found in API list: {name}")

    unique = []
    seen = set()
    for name in resolved:
        if name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _fetch_league_slugs(sport: str) -> set[str]:
    data = _get("/leagues", {"apiKey": API_KEY, "sport": sport})
    slugs = set()
    for row in data or []:
        slug = row.get("slug")
        if slug:
            slugs.add(slug)
    return slugs


def _normalize_league(slug: str) -> str:
    return LEAGUE_ALIASES.get(slug, slug)


def _is_rate_limited(error_text: str) -> bool:
    return "rate limit" in error_text.lower()


def _map_market(name: str, hdp: str | None) -> tuple[str, str] | None:
    lower = name.lower().strip()
    if lower in {"match result", "full time result", "full-time result", "1x2"}:
        return "1X2", "Full Time"
    if "both teams to score" in lower or "btts" in lower:
        return "BTTS", "BTTS"
    if "match winner" in lower or "match odds" in lower:
        return "Match Winner", "Match Winner"
    if "total games" in lower:
        spec = f"Total Games {hdp}" if hdp else "Total Games"
        return "Total Games", spec
    return None


def _iter_market_odds(market: dict) -> Iterable[dict]:
    for odds in market.get("odds", []) or []:
        yield odds


def _extract_outcomes(market_type: str, odds: dict) -> list[tuple[str, str]]:
    outcomes = []
    if market_type in {"1X2", "Match Winner"}:
        if odds.get("home"):
            outcomes.append(("home", odds["home"]))
        if odds.get("draw"):
            outcomes.append(("draw", odds["draw"]))
        if odds.get("away"):
            outcomes.append(("away", odds["away"]))
    elif market_type == "BTTS":
        if odds.get("yes"):
            outcomes.append(("yes", odds["yes"]))
        if odds.get("no"):
            outcomes.append(("no", odds["no"]))
    elif market_type == "Total Games":
        if odds.get("over"):
            label = f"over {odds.get('hdp')}" if odds.get("hdp") else "over"
            outcomes.append((label, odds["over"]))
        if odds.get("under"):
            label = f"under {odds.get('hdp')}" if odds.get("hdp") else "under"
            outcomes.append((label, odds["under"]))
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bookmakers",
        default=_load_env_value("ODDS_API_BOOKMAKERS") or "",
        help="Comma-separated bookmaker names (or set ODDS_API_BOOKMAKERS).",
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=50,
        help="Max events per sport/league.",
    )
    parser.add_argument(
        "--max-odds-requests",
        type=int,
        default=80,
        help="Max /odds requests to keep under rate limits.",
    )
    parser.add_argument(
        "--football-leagues",
        default=",".join(DEFAULT_FOOTBALL_LEAGUES),
        help="Comma-separated football leagues (slugs).",
    )
    parser.add_argument(
        "--sports",
        default="football,tennis",
        help="Comma-separated sports to fetch.",
    )
    args = parser.parse_args()

    if not API_KEY:
        raise RuntimeError("Missing ODDS_API_KEY in environment.")
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        raise RuntimeError("Missing ADMIN_EMAIL or ADMIN_PASSWORD in environment.")
    global ADMIN_TOKEN
    ADMIN_TOKEN = _get_admin_token()
    if not ADMIN_TOKEN:
        raise RuntimeError("Failed to obtain admin access token.")

    bookmakers = [b.strip() for b in args.bookmakers.split(",") if b.strip()]
    if not bookmakers:
        raise RuntimeError("Missing bookmakers list. Set ODDS_API_BOOKMAKERS or --bookmakers.")
    bookmakers = _resolve_bookmakers(bookmakers)
    if not bookmakers:
        raise RuntimeError("None of the requested bookmakers exist in the API response.")
    print(f"Using bookmakers: {', '.join(bookmakers)}")

    sports = [s.strip() for s in args.sports.split(",") if s.strip()]
    leagues = [_normalize_league(l.strip()) for l in args.football_leagues.split(",") if l.strip()]

    now = datetime.now(timezone.utc).isoformat()
    odds_items = []
    seen = set()
    odds_requests = 0

    for sport in sports:
        if sport == "football":
            available_leagues = _fetch_league_slugs("football")
            print(
                "Available football leagues:",
                ", ".join(sorted(available_leagues)),
            )
            targets = []
            for league in leagues:
                if league not in available_leagues:
                    print(f"Skipping unknown league slug: {league}")
                    continue
                targets.append((sport, league))
        else:
            targets = [(sport, None)]

        for sport_slug, league_slug in targets:
            params = {
                "apiKey": API_KEY,
                "sport": sport_slug,
                "status": "pending",
            }
            if league_slug:
                params["league"] = league_slug
            try:
                events = _get("/events", params)
            except requests.HTTPError as exc:
                response = getattr(exc, "response", None)
                detail = ""
                if response is not None:
                    detail = response.text.strip()
                print(
                    "Skipping events due to API error:",
                    f"sport={sport_slug}",
                    f"league={league_slug}",
                    detail or str(exc),
                )
                continue
            for event in (events or [])[: args.max_events]:
                if odds_requests >= args.max_odds_requests:
                    print("Reached max odds requests, stopping early.")
                    return
                event_id = event.get("id")
                if not event_id:
                    continue
                try:
                    odds_payload = _get(
                        "/odds",
                        {
                            "apiKey": API_KEY,
                            "eventId": str(event_id),
                            "bookmakers": ",".join(bookmakers),
                        },
                    )
                    odds_requests += 1
                except requests.HTTPError as exc:
                    response = getattr(exc, "response", None)
                    detail = ""
                    if response is not None:
                        detail = response.text.strip()
                    if _is_rate_limited(detail):
                        print("Rate limit hit, stopping early:", detail)
                        return
                    print(
                        "Skipping event due to API error:",
                        f"eventId={event_id}",
                        detail or str(exc),
                    )
                    continue
                if not odds_payload:
                    continue
                event_info = odds_payload.get("event", {}) or {}
                home = event_info.get("home") or event.get("home") or ""
                away = event_info.get("away") or event.get("away") or ""
                date = event_info.get("date") or event.get("date") or ""
                league = (
                    (event_info.get("league") or {}).get("slug")
                    or (event.get("league") or {}).get("slug")
                    or league_slug
                    or sport_slug
                )

                event_row = _post(
                    "/admin/events/upsert",
                    {
                        "sport": sport_slug,
                        "league": league,
                        "home_team": home,
                        "away_team": away,
                        "start_time": date,
                    },
                )
                internal_event_id = event_row["id"]

                bookmakers_data = odds_payload.get("bookmakers", {}) or {}
                urls = odds_payload.get("urls", {}) or {}

                for bookmaker_name, markets in bookmakers_data.items():
                    bookmaker = _post(
                        "/admin/bookmakers/upsert",
                        {
                            "name": bookmaker_name,
                            "region": BOOKMAKER_REGION_DEFAULT,
                            "website": urls.get(bookmaker_name, ""),
                        },
                    )
                    bookmaker_id = bookmaker["id"]

                    for market in markets or []:
                        market_name = market.get("name") or ""
                        for odds in _iter_market_odds(market):
                            hdp = odds.get("hdp")
                            mapping = _map_market(market_name, hdp)
                            if not mapping:
                                continue
                            market_type, spec = mapping
                            market_row = _post(
                                "/admin/markets/upsert",
                                {
                                    "event_id": internal_event_id,
                                    "market_type": market_type,
                                    "spec": spec,
                                    "is_live": False,
                                },
                            )
                            market_id = market_row["id"]

                            for outcome, price in _extract_outcomes(market_type, odds):
                                key = (market_id, bookmaker_id, outcome, "back", now)
                                if key in seen:
                                    continue
                                seen.add(key)
                                odds_items.append(
                                    {
                                        "market_id": market_id,
                                        "bookmaker_id": bookmaker_id,
                                        "outcome": outcome,
                                        "side": "back",
                                        "price_decimal": price,
                                        "pulled_at": now,
                                        "source": "odds_api",
                                    }
                                )

    if odds_items:
        _post("/admin/odds/batch", {"items": odds_items})
    print(f"Inserted {len(odds_items)} odds rows.")


if __name__ == "__main__":
    main()
