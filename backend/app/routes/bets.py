from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..models import Bet, User
from ..schemas import BetCreate, BetOut, BetUpdate

router = APIRouter(prefix="/bets", tags=["bets"])


@router.get("/me", response_model=list[BetOut])
def list_my_bets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    bets = (
        db.query(Bet)
        .filter(Bet.user_id == user.id)
        .order_by(Bet.placed_at.asc())
        .all()
    )
    return [
        BetOut(
            id=bet.id,
            external_key=bet.external_key,
            source=bet.source,
            event=bet.event,
            market=bet.market,
            outcome=bet.outcome,
            stake=bet.stake,
            payout=bet.payout,
            profit=bet.profit,
            odds_decimal=bet.odds_decimal,
            result=bet.result,
            placed_at=bet.placed_at,
            created_at=bet.created_at,
        )
        for bet in bets
    ]


@router.post("/me", response_model=BetOut, status_code=status.HTTP_201_CREATED)
def upsert_my_bet(
    payload: BetCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    placed_at = payload.placed_at or datetime.now(timezone.utc)
    existing = (
        db.query(Bet)
        .filter(Bet.user_id == user.id, Bet.external_key == payload.external_key)
        .first()
    )
    if existing:
        existing.source = payload.source
        existing.event = payload.event
        existing.market = payload.market
        existing.outcome = payload.outcome
        existing.stake = payload.stake
        existing.payout = payload.payout
        existing.profit = payload.profit
        existing.placed_at = placed_at
        db.commit()
        db.refresh(existing)
        bet = existing
    else:
        bet = Bet(
            user_id=user.id,
            external_key=payload.external_key,
            source=payload.source,
            event=payload.event,
            market=payload.market,
            outcome=payload.outcome,
            stake=payload.stake,
            payout=payload.payout,
            profit=payload.profit,
            placed_at=placed_at,
        )
        db.add(bet)
        db.commit()
        db.refresh(bet)
    return BetOut(
        id=bet.id,
        external_key=bet.external_key,
        source=bet.source,
        event=bet.event,
        market=bet.market,
        outcome=bet.outcome,
        stake=bet.stake,
        payout=bet.payout,
        profit=bet.profit,
        odds_decimal=bet.odds_decimal,
        result=bet.result,
        placed_at=bet.placed_at,
        created_at=bet.created_at,
    )


@router.patch("/me/{bet_id}", response_model=BetOut)
def update_my_bet(
    bet_id: str,
    payload: BetUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    bet = db.query(Bet).filter(Bet.user_id == user.id, Bet.id == bet_id).first()
    if not bet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bet not found.")

    if payload.odds_decimal is not None:
        bet.odds_decimal = payload.odds_decimal

    if payload.result is not None:
        bet.result = payload.result

    result = bet.result or "pending"
    stake = bet.stake
    odds = bet.odds_decimal
    if result == "win":
        if not odds or odds <= 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Odds must be set for a winning bet.",
            )
        bet.payout = stake * odds
        bet.profit = bet.payout - stake
    elif result == "loss":
        bet.payout = 0
        bet.profit = -stake
    elif result == "void":
        bet.payout = stake
        bet.profit = 0
    elif result == "pending":
        bet.payout = stake
        bet.profit = 0

    db.commit()
    db.refresh(bet)
    return BetOut(
        id=bet.id,
        external_key=bet.external_key,
        source=bet.source,
        event=bet.event,
        market=bet.market,
        outcome=bet.outcome,
        stake=bet.stake,
        payout=bet.payout,
        profit=bet.profit,
        odds_decimal=bet.odds_decimal,
        result=bet.result,
        placed_at=bet.placed_at,
        created_at=bet.created_at,
    )


@router.delete("/me/{bet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_bet(
    bet_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    bet = db.query(Bet).filter(Bet.user_id == user.id, Bet.id == bet_id).first()
    if not bet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bet not found.")
    db.delete(bet)
    db.commit()
    return None


@router.delete("/me/by-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_my_bet_by_key(
    external_key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    bet = (
        db.query(Bet)
        .filter(Bet.user_id == user.id, Bet.external_key == external_key)
        .first()
    )
    if not bet:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bet not found.")
    db.delete(bet)
    db.commit()
    return None


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_my_bets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Bet).filter(Bet.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return None
