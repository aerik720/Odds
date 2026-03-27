from decimal import Decimal
import json
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .auth import ensure_admin_user, get_current_user
from .db import SessionLocal, get_db
from .routes.auth import router as auth_router
from .routes.bets import router as bets_router
from .routes.admin import router as admin_router
from .models import Bookmaker, Market
from .services.arbitrage_service import (
    debug_back_lay_matches,
    debug_event_keys,
    find_back_lay_arbs,
)
from .services.surebet_service import get_surebets
from .surebet import find_surebets, stake_split
from .testdata import sample_odds

ROOT_DIR = Path(__file__).resolve().parents[2]

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?|https?://([a-z0-9-]+\.)?onrender\.com",
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router)
app.include_router(bets_router)
app.include_router(admin_router)


@app.on_event("startup")
def bootstrap_admin() -> None:
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/demo/surebets")
def demo_surebets(_user=Depends(get_current_user)):
    odds = sample_odds()
    results = find_surebets(odds)
    payload = []
    for result in results:
        stakes = stake_split(Decimal("100.00"), result.best_odds)
        payload.append(
            {
                "market_id": result.market_id,
                "total_implied_prob": str(result.total_implied_prob),
                "edge_pct": str(result.edge_pct),
                "best_odds": {
                    k: {
                        "price_decimal": str(v.price_decimal),
                        "bookmaker": v.bookmaker,
                    }
                    for k, v in result.best_odds.items()
                },
                "stakes_for_100": {k: str(v) for k, v in stakes.items()},
            }
        )
    return payload


@app.get("/surebets")
def surebets(
    total_stake: float = 100.0,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    results = get_surebets(db)
    market_ids = [result.market_id for result in results]
    markets = (
        db.query(Market)
        .filter(Market.id.in_(market_ids))
        .all()
        if market_ids
        else []
    )
    market_map = {
        market.id: {
            "event": f"{market.event.home_team} vs {market.event.away_team}",
            "market_type": market.market_type,
            "spec": market.spec,
            "event_start_time": (
                market.event.start_time.isoformat()
                if market.event.start_time
                else ""
            ),
        }
        for market in markets
    }
    bookmaker_map = {
        bookmaker.name: bookmaker.website
        for bookmaker in db.query(Bookmaker).all()
    }
    return [
        {
            "market_id": result.market_id,
            "event": market_map.get(result.market_id, {}).get("event", ""),
            "market_type": market_map.get(result.market_id, {}).get("market_type", ""),
            "spec": market_map.get(result.market_id, {}).get("spec", ""),
            "event_start_time": market_map.get(result.market_id, {}).get(
                "event_start_time", ""
            ),
            "total_implied_prob": str(result.total_implied_prob),
            "edge_pct": str(result.edge_pct),
            "best_odds": {
                k: {
                    "price_decimal": str(v.price_decimal),
                    "bookmaker": v.bookmaker,
                    "bookmaker_website": bookmaker_map.get(v.bookmaker),
                }
                for k, v in result.best_odds.items()
            },
            "stakes": {
                k: str(v)
                for k, v in stake_split(
                    Decimal(str(total_stake)), result.best_odds
                ).items()
            },
        }
        for result in results
    ]


@app.get("/arbitrage/back-lay")
def back_lay_arbitrage(
    commission: float = 0.02,
    allow_same_bookmaker: bool = False,
    match_events: bool = True,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    results = find_back_lay_arbs(
        db,
        Decimal(str(commission)),
        allow_same_bookmaker=allow_same_bookmaker,
        match_events=match_events,
    )
    market_ids = [result["market_id"] for result in results if "market_id" in result]
    markets = (
        db.query(Market)
        .filter(Market.id.in_(market_ids))
        .all()
        if market_ids
        else []
    )
    market_map = {
        market.id: {
            "event": f"{market.event.home_team} vs {market.event.away_team}",
            "event_start_time": (
                market.event.start_time.isoformat()
                if market.event.start_time
                else ""
            ),
        }
        for market in markets
    }
    for result in results:
        market_id = result.get("market_id")
        if market_id and market_id in market_map:
            result["event"] = market_map[market_id]["event"]
            result["event_start_time"] = market_map[market_id]["event_start_time"]
    return results


@app.get("/arbitrage/debug/back-lay")
def debug_back_lay(db: Session = Depends(get_db), _user=Depends(get_current_user)):
    return debug_back_lay_matches(db)


@app.get("/arbitrage/debug/event-keys")
def debug_event_keys_endpoint(
    limit_per_bookmaker: int = 50,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    return debug_event_keys(db, limit_per_bookmaker=limit_per_bookmaker)


def _load_odds_api_arbitrage() -> list[dict]:
    candidates = [
        ROOT_DIR / "backend" / "data" / "odds_api_arbitrage.json",
        ROOT_DIR / "backend" / "backend" / "data" / "odds_api_arbitrage.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
    return []


def _load_valuebets() -> list[dict]:
    candidates = [
        ROOT_DIR / "backend" / "data" / "valuebets_smarkets.json",
        ROOT_DIR / "backend" / "backend" / "data" / "valuebets_smarkets.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return []
    return []


@app.get("/arbitrage/odds-api")
def odds_api_arbitrage(_user=Depends(get_current_user)):
    payload = _load_odds_api_arbitrage()
    for item in payload:
        event = item.get("event") or {}
        home = event.get("home", "")
        away = event.get("away", "")
        if home and away:
            item["event_name"] = f"{home} vs {away}"
        item["event_start_time"] = event.get("date", "")
    return payload


@app.get("/valuebets")
def valuebets(min_ev: float = 105.0, _user=Depends(get_current_user)):
    payload = _load_valuebets()
    filtered = []
    for item in payload:
        valuebet = item.get("valuebet") or {}
        ev = valuebet.get("expectedValue")
        try:
            ev_num = float(ev)
        except (TypeError, ValueError):
            ev_num = None
        if ev_num is None or ev_num < min_ev:
            continue
        event = valuebet.get("event") or {}
        home = event.get("home", "")
        away = event.get("away", "")
        if home and away:
            item["event_name"] = f"{home} vs {away}"
        filtered.append(item)
    return filtered
