import os
from datetime import datetime, timezone

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def _post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    bookmaker = _post(
        "/admin/bookmakers",
        {"name": "BookieA", "region": "SE", "website": "https://bookiea.test"},
    )
    event = _post(
        "/admin/events",
        {
            "sport": "football",
            "league": "Allsvenskan",
            "home_team": "AIK",
            "away_team": "Hammarby",
            "start_time": datetime(2025, 5, 20, 18, 0, tzinfo=timezone.utc).isoformat(),
        },
    )
    market = _post(
        "/admin/markets",
        {
            "event_id": event["id"],
            "market_type": "1X2",
            "spec": "1X2",
            "is_live": False,
        },
    )
    _post(
        "/admin/odds/batch",
        {
            "items": [
                {
                    "market_id": market["id"],
                    "bookmaker_id": bookmaker["id"],
                    "outcome": "home",
                    "price_decimal": 2.20,
                    "pulled_at": datetime.now(timezone.utc).isoformat(),
                    "source": "bootstrap",
                }
            ]
        },
    )
    print("Created:", {"bookmaker_id": bookmaker["id"], "event_id": event["id"], "market_id": market["id"]})


if __name__ == "__main__":
    main()
