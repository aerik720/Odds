from decimal import Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import Bookmaker, Odd
from ..surebet import OddInput, SurebetResult, find_surebets


def _best_latest_odds(session: Session) -> list[OddInput]:
    latest = (
        select(
            Odd.market_id,
            Odd.bookmaker_id,
            Odd.outcome,
            func.max(Odd.pulled_at).label("pulled_at"),
        )
        .where(Odd.side == "back")
        .group_by(Odd.market_id, Odd.bookmaker_id, Odd.outcome)
        .subquery()
    )

    latest_rows = (
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

    ranked = (
        select(
            latest_rows.c.market_id,
            latest_rows.c.outcome,
            latest_rows.c.price_decimal,
            latest_rows.c.bookmaker_id,
            func.row_number()
            .over(
                partition_by=[latest_rows.c.market_id, latest_rows.c.outcome],
                order_by=latest_rows.c.price_decimal.desc(),
            )
            .label("rn"),
        )
        .subquery()
    )

    rows = session.execute(
        select(
            ranked.c.market_id,
            ranked.c.outcome,
            ranked.c.price_decimal,
            Bookmaker.name,
        )
        .join(Bookmaker, Bookmaker.id == ranked.c.bookmaker_id)
        .where(ranked.c.rn == 1)
    ).all()

    return [
        OddInput(
            market_id=row.market_id,
            outcome=row.outcome,
            price_decimal=Decimal(row.price_decimal),
            bookmaker=row.name,
        )
        for row in rows
    ]


def get_surebets(session: Session) -> list[SurebetResult]:
    odds = _best_latest_odds(session)
    return find_surebets(odds)
