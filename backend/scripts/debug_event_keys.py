import argparse

from app.db import SessionLocal
from app import models
from app.services import arbitrage_service as arb


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bookmaker", required=True)
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--market-type", default="1X2")
    args = parser.parse_args()

    db = SessionLocal()
    bookmaker = (
        db.query(models.Bookmaker)
        .filter(models.Bookmaker.name == args.bookmaker)
        .first()
    )
    if not bookmaker:
        print(f"Bookmaker not found: {args.bookmaker}")
        return

    rows = (
        db.query(
            models.Event.home_team,
            models.Event.away_team,
            models.Event.start_time,
            models.Market.market_type,
            models.Market.spec,
            models.Odd.outcome,
            models.Odd.price_decimal,
        )
        .join(models.Market, models.Market.event_id == models.Event.id)
        .join(models.Odd, models.Odd.market_id == models.Market.id)
        .filter(models.Odd.bookmaker_id == bookmaker.id)
        .filter(models.Event.home_team.like(f"%{args.home}%"))
        .filter(models.Event.away_team.like(f"%{args.away}%"))
        .filter(models.Market.market_type == args.market_type)
        .all()
    )

    for r in rows:
        key = (
            arb._normalize_team(r.home_team),
            arb._normalize_team(r.away_team),
            (r.market_type or "").strip().upper(),
            arb._normalize_spec(r.market_type, r.spec),
            arb._time_bucket(r.start_time),
        )
        print(
            r.home_team,
            "vs",
            r.away_team,
            r.outcome,
            r.price_decimal,
            "key=",
            key,
        )


if __name__ == "__main__":
    main()
