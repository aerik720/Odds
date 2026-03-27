from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, select


ROOT_DIR = Path(__file__).resolve().parents[1]


def _get_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value else None


def _normalize_postgres_url(url: str) -> str:
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    return url


def _load_table(engine, name: str) -> Table:
    metadata = MetaData()
    return Table(name, metadata, autoload_with=engine)


def _load_valuebets() -> list[dict[str, Any]]:
    candidates = [
        ROOT_DIR / "data" / "valuebets_smarkets.json",
        ROOT_DIR / "backend" / "data" / "valuebets_smarkets.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return []


def _market_label(market: dict[str, Any]) -> str:
    name = market.get("name") or ""
    hdp = market.get("hdp")
    if hdp not in (None, ""):
        return f"{name} {hdp}"
    return name or "Market"


def _event_name(item: dict[str, Any]) -> str:
    if item.get("event_name"):
        return item["event_name"]
    event = item.get("valuebet", {}).get("event", {}) or {}
    home = event.get("home") or ""
    away = event.get("away") or ""
    if home and away:
        return f"{home} vs {away}"
    return "Unknown event"


def _legacy_key(item: dict[str, Any]) -> str:
    valuebet = item.get("valuebet", {}) or {}
    event_name = _event_name(item)
    market = valuebet.get("market", {}) or {}
    market_label = _market_label(market)
    side = valuebet.get("betSide") or ""
    return "|".join(["valuebet", event_name, market_label, str(side)])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate old valuebet placed keys to valuebet:<id> and assign to admin."
    )
    parser.add_argument("--admin-email", default=None)
    args = parser.parse_args()

    postgres_url = _get_env("DATABASE_URL")
    if not postgres_url:
        raise RuntimeError("Missing DATABASE_URL in environment.")
    postgres_url = _normalize_postgres_url(postgres_url)

    admin_email = args.admin_email or _get_env("ADMIN_EMAIL")
    if not admin_email:
        raise RuntimeError("Missing ADMIN_EMAIL (or pass --admin-email).")

    engine = create_engine(postgres_url)
    users = _load_table(engine, "users")
    bets = _load_table(engine, "bets")

    with engine.connect() as conn:
        admin_row = conn.execute(
            select(users.c.id).where(users.c.email == admin_email)
        ).first()
        if not admin_row:
            raise RuntimeError(f"Admin user not found for email: {admin_email}")
        admin_id = admin_row[0]

        valuebets = _load_valuebets()
        mapping: dict[str, str] = {}
        for item in valuebets:
            vb = item.get("valuebet", {}) or {}
            vb_id = vb.get("id")
            if not vb_id:
                continue
            mapping[_legacy_key(item)] = f"valuebet:{vb_id}"

        legacy_rows = conn.execute(
            select(bets).where(
                bets.c.source == "valuebet",
                bets.c.external_key.like("valuebet|%"),
            )
        ).fetchall()

        updated = 0
        deleted = 0
        skipped = 0

        for row in legacy_rows:
            data = dict(row._mapping)
            old_key = data.get("external_key")
            new_key = mapping.get(old_key)
            if not new_key:
                skipped += 1
                continue

            existing = conn.execute(
                select(bets.c.id).where(
                    bets.c.user_id == admin_id,
                    bets.c.external_key == new_key,
                )
            ).first()

            if existing:
                conn.execute(bets.delete().where(bets.c.id == data["id"]))
                deleted += 1
                continue

            conn.execute(
                bets.update()
                .where(bets.c.id == data["id"])
                .values(user_id=admin_id, external_key=new_key)
            )
            updated += 1

        print(f"Legacy placed bets: {len(legacy_rows)}")
        print(f"Updated: {updated}")
        print(f"Deleted (duplicates): {deleted}")
        print(f"Skipped (no match): {skipped}")


if __name__ == "__main__":
    main()
