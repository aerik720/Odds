import argparse
import os
from pathlib import Path

import requests

API_BASE = "https://api.the-odds-api.com/v4"
SESSION = requests.Session()
SESSION.trust_env = False


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
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sport",
        default="soccer_epl",
        help="Sport key (v4). Example: soccer_epl",
    )
    parser.add_argument(
        "--regions",
        default="uk",
        help="Comma-separated regions (default: uk).",
    )
    parser.add_argument(
        "--markets",
        default="h2h",
        help="Comma-separated markets (default: h2h).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Max events to scan (default: 3).",
    )
    args = parser.parse_args()

    api_key = _load_env_value("SMARKETS_ODDS_API_KEY") or _load_env_value(
        "SMARKET_ODDS_API_KEY"
    )
    if not api_key:
        raise RuntimeError("Missing SMARKET_ODDS_API_KEY in environment.")

    params = {
        "apiKey": api_key,
        "regions": args.regions,
        "markets": args.markets,
        "oddsFormat": "decimal",
    }
    events = _get(f"/sports/{args.sport}/odds", params)
    if not events:
        print("No events returned. Try a different sport/region.")
        return

    keys: dict[str, str] = {}
    scanned = 0
    for event in events:
        scanned += 1
        for bookmaker in event.get("bookmakers", []) or []:
            key = bookmaker.get("key")
            title = bookmaker.get("title") or ""
            if key and key not in keys:
                keys[key] = title
        if scanned >= args.limit:
            break

    print(f"Scanned {scanned} event(s). Found {len(keys)} bookmakers:")
    for key in sorted(keys.keys()):
        title = keys[key]
        label = f"{key} ({title})" if title else key
        print(f"- {label}")

    smarkets_key = next(
        (key for key, title in keys.items() if "smarkets" in key.lower() or "smarkets" in title.lower()),
        None,
    )
    if smarkets_key:
        print(f"Smarkets key detected: {smarkets_key}")
    else:
        print("Smarkets key not detected in this sample.")


if __name__ == "__main__":
    main()
