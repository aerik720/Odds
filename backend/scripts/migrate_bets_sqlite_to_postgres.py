from __future__ import annotations

import argparse
import os
from typing import Any, Iterable

from sqlalchemy import MetaData, Table, create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine


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


def _load_table(engine: Engine, name: str) -> Table:
    metadata = MetaData()
    return Table(name, metadata, autoload_with=engine)


def _chunked(rows: Iterable[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _resolve_user_id(pg_engine: Engine, email: str) -> str:
    users = _load_table(pg_engine, "users")
    with pg_engine.connect() as conn:
        row = conn.execute(select(users.c.id).where(users.c.email == email)).first()
    if not row:
        raise RuntimeError(f"User not found in Postgres for email: {email}")
    return row[0]


def _fetch_sqlite_bets(sql_engine: Engine) -> list[dict[str, Any]]:
    bets = _load_table(sql_engine, "bets")
    with sql_engine.connect() as conn:
        rows = conn.execute(select(bets)).fetchall()
    return [dict(row._mapping) for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate bets from SQLite to Postgres.")
    parser.add_argument("--sqlite-path", default="backend/app.db")
    parser.add_argument("--target-email", required=True)
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    postgres_url = _get_env("DATABASE_URL")
    if not postgres_url:
        raise RuntimeError("Missing DATABASE_URL in environment.")
    postgres_url = _normalize_postgres_url(postgres_url)

    sqlite_url = f"sqlite:///{args.sqlite_path}"
    sql_engine = create_engine(sqlite_url)
    pg_engine = create_engine(postgres_url)

    target_user_id = _resolve_user_id(pg_engine, args.target_email)

    sqlite_bets = _fetch_sqlite_bets(sql_engine)
    if not sqlite_bets:
        print("No bets found in SQLite.")
        return

    pg_bets = _load_table(pg_engine, "bets")
    pg_columns = {col.name for col in pg_bets.columns}

    def normalize(row: dict[str, Any]) -> dict[str, Any]:
        data = {k: v for k, v in row.items() if k in pg_columns}
        data["user_id"] = target_user_id
        if "odds_decimal" in pg_columns and "odds_decimal" not in data:
            data["odds_decimal"] = None
        if "result" in pg_columns and "result" not in data:
            data["result"] = "pending"
        return data

    rows = [normalize(row) for row in sqlite_bets]

    inserted = 0
    with pg_engine.begin() as conn:
        for batch in _chunked(rows, args.batch_size):
            stmt = pg_insert(pg_bets).values(batch)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["user_id", "external_key"]
            )
            result = conn.execute(stmt)
            inserted += result.rowcount or 0

    print(f"SQLite bets: {len(sqlite_bets)}")
    print(f"Inserted into Postgres: {inserted}")
    print(f"Skipped (duplicates or conflicts): {len(sqlite_bets) - inserted}")


if __name__ == "__main__":
    main()
