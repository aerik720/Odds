from datetime import datetime, timedelta, timezone
import re
import requests

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db, _load_env_value
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
            event_id=bet.event_id,
            source=bet.source,
            event=bet.event,
            market=bet.market,
            outcome=bet.outcome,
            stake=bet.stake,
            payout=bet.payout,
            profit=bet.profit,
            odds_decimal=bet.odds_decimal,
            result=bet.result,
            event_start_time=bet.event_start_time,
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
        existing.event_id = payload.event_id
        existing.event = payload.event
        existing.market = payload.market
        existing.outcome = payload.outcome
        existing.stake = payload.stake
        existing.payout = payload.payout
        existing.profit = payload.profit
        existing.event_start_time = payload.event_start_time
        existing.placed_at = placed_at
        db.commit()
        db.refresh(existing)
        bet = existing
    else:
        bet = Bet(
            user_id=user.id,
            external_key=payload.external_key,
            event_id=payload.event_id,
            source=payload.source,
            event=payload.event,
            market=payload.market,
            outcome=payload.outcome,
            stake=payload.stake,
            payout=payload.payout,
            profit=payload.profit,
            event_start_time=payload.event_start_time,
            placed_at=placed_at,
        )
        db.add(bet)
        db.commit()
        db.refresh(bet)
    return BetOut(
        id=bet.id,
        external_key=bet.external_key,
        event_id=bet.event_id,
        source=bet.source,
        event=bet.event,
        market=bet.market,
        outcome=bet.outcome,
        stake=bet.stake,
        payout=bet.payout,
        profit=bet.profit,
        odds_decimal=bet.odds_decimal,
        result=bet.result,
        event_start_time=bet.event_start_time,
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
        event_id=bet.event_id,
        source=bet.source,
        event=bet.event,
        market=bet.market,
        outcome=bet.outcome,
        stake=bet.stake,
        payout=bet.payout,
        profit=bet.profit,
        odds_decimal=bet.odds_decimal,
        result=bet.result,
        event_start_time=bet.event_start_time,
        placed_at=bet.placed_at,
        created_at=bet.created_at,
    )


def _internal_api_base() -> str:
    env_base = _load_env_value("API_BASE_URL")
    if env_base:
        return env_base.rstrip("/")
    port = _load_env_value("PORT")
    if port:
        return f"http://127.0.0.1:{port}"
    return "http://127.0.0.1:8000"


def _is_final_status(status: str | None) -> bool:
    if not status:
        return False
    value = status.strip().lower()
    return value in {"finished", "final", "complete", "completed", "closed", "settled", "ended"}


def _parse_line(text: str) -> float | None:
    if not text:
        return None
    match = re.findall(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match[-1])
    except ValueError:
        return None


def _is_totals_market(label: str) -> bool:
    value = label.lower()
    return "total" in value or "totals" in value


def _is_spread_market(label: str) -> bool:
    value = label.lower()
    return "spread" in value or "handicap" in value


def _is_moneyline_market(label: str) -> bool:
    value = label.lower()
    return any(token in value for token in ["moneyline", "match result", "matchresult", "1x2", "ml"])


def _has_half_time(label: str) -> bool:
    value = label.lower()
    return "ht" in value or "half" in value


def _compute_result(bet: Bet, home: int | float, away: int | float) -> str | None:
    market = bet.market or ""
    outcome = (bet.outcome or "").strip().lower()
    if _has_half_time(market):
        return None
    if _is_totals_market(market):
        line = _parse_line(outcome) or _parse_line(market)
        if line is None:
            return None
        total = float(home) + float(away)
        if outcome.startswith("over"):
            if total > line:
                return "win"
            if total < line:
                return "loss"
            return "void"
        if outcome.startswith("under"):
            if total < line:
                return "win"
            if total > line:
                return "loss"
            return "void"
        return None
    if _is_spread_market(market):
        line = _parse_line(market)
        if line is None:
            return None
        home_adj = float(home)
        away_adj = float(away)
        if outcome in {"home", "h"}:
            home_adj += line
        elif outcome in {"away", "a"}:
            away_adj += line
        else:
            return None
        if home_adj > away_adj:
            return "win" if outcome in {"home", "h"} else "loss"
        if home_adj < away_adj:
            return "win" if outcome in {"away", "a"} else "loss"
        return "void"
    if _is_moneyline_market(market):
        if outcome in {"home", "h"}:
            if home > away:
                return "win"
            if home < away:
                return "loss"
            return "void"
        if outcome in {"away", "a"}:
            if away > home:
                return "win"
            if away < home:
                return "loss"
            return "void"
        if outcome in {"draw", "tie", "x"}:
            if home == away:
                return "win"
            return "loss"
    return None


def _apply_result(bet: Bet, result: str) -> bool:
    stake = bet.stake
    odds = bet.odds_decimal
    if result == "win":
        if not odds or odds <= 1:
            return False
        bet.payout = stake * odds
        bet.profit = bet.payout - stake
    elif result == "loss":
        bet.payout = 0
        bet.profit = -stake
    elif result == "void":
        bet.payout = stake
        bet.profit = 0
    else:
        bet.payout = stake
        bet.profit = 0
    bet.result = result
    return True


@router.post("/me/refresh-results")
def refresh_bet_results(
    min_hours: int = 2,
    max_events: int = 25,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    api_key = _load_env_value("ODDS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="ODDS_API_KEY not configured")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=min_hours)
    pending = (
        db.query(Bet)
        .filter(
            Bet.user_id == user.id,
            Bet.result == "pending",
            Bet.event_id.isnot(None),
            Bet.event_start_time.isnot(None),
            Bet.event_start_time <= cutoff,
        )
        .order_by(Bet.event_start_time.asc())
        .all()
    )
    event_ids = []
    for bet in pending:
        if bet.event_id and bet.event_id not in event_ids:
            event_ids.append(bet.event_id)
        if len(event_ids) >= max_events:
            break

    updated = 0
    checked = 0
    skipped = 0
    for event_id in event_ids:
        try:
            resp = requests.get(
                f"https://api2.odds-api.io/v3/events/{event_id}",
                params={"apiKey": api_key},
                timeout=25,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            skipped += 1
            continue

        status = payload.get("status")
        scores = payload.get("scores") or {}
        if not _is_final_status(status):
            continue

        home_score = scores.get("home")
        away_score = scores.get("away")
        if home_score is None or away_score is None:
            continue

        bets_for_event = [bet for bet in pending if str(bet.event_id) == str(event_id)]
        for bet in bets_for_event:
            checked += 1
            result = _compute_result(bet, home_score, away_score)
            if result is None or result == "pending":
                continue
            if _apply_result(bet, result):
                updated += 1
        db.commit()

    return {"checked": checked, "updated": updated, "skipped": skipped}


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
