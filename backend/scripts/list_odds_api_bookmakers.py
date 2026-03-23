import json
from pathlib import Path

import requests

API_BASE = "https://api.odds-api.io/v3"
SESSION = requests.Session()
SESSION.trust_env = False


def main() -> None:
    resp = SESSION.get(f"{API_BASE}/bookmakers", timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    output_path = Path("backend/data/odds_api_bookmakers.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    names = [item.get("name") for item in payload if item.get("name")]
    print(f"Wrote {len(payload)} bookmakers to {output_path}.")
    if names:
        print("Bookmakers:")
        for name in sorted(names):
            print(f"- {name}")


if __name__ == "__main__":
    main()
