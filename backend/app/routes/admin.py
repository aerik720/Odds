import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import hash_password, require_admin
from ..db import get_db
from ..models import Bookmaker, Event, EventAlias, Market, MarketAlias, Odd, User
from ..schemas import (
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    BookmakerCreate,
    EventCreate,
    EventAliasCreate,
    MarketCreate,
    MarketAliasCreate,
    OddBatchCreate,
    UpsertResponse,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])

TASKS = {
    "run_odds_api": "backend/scripts/run_odds_api.ps1",
    "run_odds_api_arbitrage": "backend/scripts/run_odds_api_arbitrage.ps1",
    "run_valuebets_smarkets": "backend/scripts/run_valuebets_smarkets.ps1",
}

ROOT_DIR = Path(__file__).resolve().parents[3]
TASK_STATUS: dict[str, dict] = {}

PROGRESS_RE = re.compile(r"Step\s+(\d+)\s*/\s*(\d+)")
LOG_LIMIT = 8000


def _truncate(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def _append_log(name: str, key: str, line: str) -> None:
    status = TASK_STATUS.setdefault(name, {})
    current = status.get(key, "")
    status[key] = _truncate(f"{current}{line}", LOG_LIMIT)


def _set_progress(name: str, line: str) -> None:
    match = PROGRESS_RE.search(line)
    if not match:
        return
    current, total = match.groups()
    try:
        value = int(current) / int(total)
    except (ValueError, ZeroDivisionError):
        return
    status = TASK_STATUS.setdefault(name, {})
    status["progress"] = value
    status["step"] = line.strip()


def _track_process(name: str, process: subprocess.Popen) -> None:
    status = TASK_STATUS.setdefault(name, {})
    status["status"] = "running"
    status["started_at"] = datetime.now(timezone.utc).isoformat()
    status["progress"] = status.get("progress", 0.0)
    status["step"] = status.get("step", "")
    status["stdout"] = status.get("stdout", "")
    status["stderr"] = status.get("stderr", "")

    def read_stream(stream, key: str) -> None:
        for line in iter(stream.readline, ""):
            _append_log(name, key, line)
            if key == "stdout":
                _set_progress(name, line)
        stream.close()

    stdout_thread = threading.Thread(
        target=read_stream, args=(process.stdout, "stdout"), daemon=True
    )
    stderr_thread = threading.Thread(
        target=read_stream, args=(process.stderr, "stderr"), daemon=True
    )
    stdout_thread.start()
    stderr_thread.start()

    process.wait()
    stdout_thread.join()
    stderr_thread.join()

    status["returncode"] = process.returncode
    status["finished_at"] = datetime.now(timezone.utc).isoformat()
    status["status"] = "finished" if process.returncode == 0 else "error"


def _env_path() -> Path:
    return ROOT_DIR / "backend" / ".env"


def _read_env() -> dict[str, str]:
    env_file = _env_path()
    if not env_file.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"')
    return values


def _write_env(values: dict[str, str]) -> None:
    env_file = _env_path()
    lines = []
    existing = {}
    if env_file.exists():
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.rstrip("\n")
            if not line or line.lstrip().startswith("#") or "=" not in line:
                lines.append(line)
                continue
            key, _, _ = line.partition("=")
            key = key.strip()
            existing[key] = True
            if key in values:
                lines.append(f'{key}="{values[key]}"')
            else:
                lines.append(line)
    for key, value in values.items():
        if key not in existing:
            lines.append(f'{key}="{value}"')
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    event = Event(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": str(event.id)}


@router.post("/events/upsert", response_model=UpsertResponse)
def upsert_event(payload: EventCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(Event).where(
            Event.sport == payload.sport,
            Event.league == payload.league,
            Event.home_team == payload.home_team,
            Event.away_team == payload.away_team,
            Event.start_time == payload.start_time,
        )
    ).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "created": False}
    event = Event(**payload.model_dump())
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"id": event.id, "created": True}


@router.post("/markets", status_code=status.HTTP_201_CREATED)
def create_market(payload: MarketCreate, db: Session = Depends(get_db)):
    exists = db.execute(select(Event.id).where(Event.id == payload.event_id)).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="event not found")
    market = Market(**payload.model_dump())
    db.add(market)
    db.commit()
    db.refresh(market)
    return {"id": str(market.id)}


@router.post("/markets/upsert", response_model=UpsertResponse)
def upsert_market(payload: MarketCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(Market).where(
            Market.event_id == str(payload.event_id),
            Market.market_type == payload.market_type,
            Market.spec == payload.spec,
            Market.is_live == payload.is_live,
        )
    ).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "created": False}
    market = Market(**payload.model_dump())
    db.add(market)
    db.commit()
    db.refresh(market)
    return {"id": market.id, "created": True}


@router.post("/bookmakers", status_code=status.HTTP_201_CREATED)
def create_bookmaker(payload: BookmakerCreate, db: Session = Depends(get_db)):
    bookmaker = Bookmaker(**payload.model_dump())
    db.add(bookmaker)
    db.commit()
    db.refresh(bookmaker)
    return {"id": str(bookmaker.id)}


@router.post("/bookmakers/upsert", response_model=UpsertResponse)
def upsert_bookmaker(payload: BookmakerCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(Bookmaker).where(Bookmaker.name == payload.name)
    ).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "created": False}
    bookmaker = Bookmaker(**payload.model_dump())
    db.add(bookmaker)
    db.commit()
    db.refresh(bookmaker)
    return {"id": bookmaker.id, "created": True}


@router.post("/event-aliases/upsert", response_model=UpsertResponse)
def upsert_event_alias(payload: EventAliasCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(EventAlias).where(
            EventAlias.bookmaker_id == payload.bookmaker_id,
            EventAlias.external_event_id == payload.external_event_id,
        )
    ).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "created": False}
    alias = EventAlias(**payload.model_dump())
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return {"id": alias.id, "created": True}


@router.post("/market-aliases/upsert", response_model=UpsertResponse)
def upsert_market_alias(payload: MarketAliasCreate, db: Session = Depends(get_db)):
    existing = db.execute(
        select(MarketAlias).where(
            MarketAlias.bookmaker_id == payload.bookmaker_id,
            MarketAlias.external_market_id == payload.external_market_id,
        )
    ).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "created": False}
    alias = MarketAlias(**payload.model_dump())
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return {"id": alias.id, "created": True}


@router.get("/event-aliases/resolve")
def resolve_event_alias(
    bookmaker_id: str, external_event_id: str, db: Session = Depends(get_db)
):
    alias = db.execute(
        select(EventAlias).where(
            EventAlias.bookmaker_id == bookmaker_id,
            EventAlias.external_event_id == external_event_id,
        )
    ).scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alias not found")
    return {"event_id": alias.event_id}


@router.get("/market-aliases/resolve")
def resolve_market_alias(
    bookmaker_id: str, external_market_id: str, db: Session = Depends(get_db)
):
    alias = db.execute(
        select(MarketAlias).where(
            MarketAlias.bookmaker_id == bookmaker_id,
            MarketAlias.external_market_id == external_market_id,
        )
    ).scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alias not found")
    return {"market_id": alias.market_id}


@router.get("/event-aliases")
def list_event_aliases(bookmaker_id: str | None = None, db: Session = Depends(get_db)):
    query = select(EventAlias)
    if bookmaker_id:
        query = query.where(EventAlias.bookmaker_id == bookmaker_id)
    aliases = db.execute(query).scalars().all()
    return [
        {
            "id": alias.id,
            "bookmaker_id": alias.bookmaker_id,
            "event_id": alias.event_id,
            "external_event_id": alias.external_event_id,
        }
        for alias in aliases
    ]


@router.get("/market-aliases")
def list_market_aliases(bookmaker_id: str | None = None, db: Session = Depends(get_db)):
    query = select(MarketAlias)
    if bookmaker_id:
        query = query.where(MarketAlias.bookmaker_id == bookmaker_id)
    aliases = db.execute(query).scalars().all()
    return [
        {
            "id": alias.id,
            "bookmaker_id": alias.bookmaker_id,
            "market_id": alias.market_id,
            "external_market_id": alias.external_market_id,
        }
        for alias in aliases
    ]


@router.post("/odds/batch", status_code=status.HTTP_201_CREATED)
def create_odds_batch(payload: OddBatchCreate, db: Session = Depends(get_db)):
    if not payload.items:
        return {"created": 0}

    market_ids = {item.market_id for item in payload.items}
    bookmaker_ids = {item.bookmaker_id for item in payload.items}

    existing_markets = set(
        db.execute(select(Market.id).where(Market.id.in_(market_ids))).scalars().all()
    )
    existing_bookmakers = set(
        db.execute(select(Bookmaker.id).where(Bookmaker.id.in_(bookmaker_ids)))
        .scalars()
        .all()
    )

    missing_markets = market_ids - existing_markets
    missing_bookmakers = bookmaker_ids - existing_bookmakers
    if missing_markets or missing_bookmakers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "missing_markets": [str(mid) for mid in sorted(missing_markets)],
                "missing_bookmakers": [str(bid) for bid in sorted(missing_bookmakers)],
            },
        )

    rows = [
        Odd(
            market_id=item.market_id,
            bookmaker_id=item.bookmaker_id,
            outcome=item.outcome,
            side=item.side,
            price_decimal=item.price_decimal,
            pulled_at=item.pulled_at,
            source=item.source,
        )
        for item in payload.items
    ]
    db.add_all(rows)
    db.commit()
    return {"created": len(rows)}


def _user_out(user: User) -> AdminUserOut:
    return AdminUserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(db: Session = Depends(get_db)):
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return [_user_out(user) for user in users]


@router.post("/users", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )
    user = User(
        email=payload.email,
        role=payload.role,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.patch("/users/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: str,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_admin),
):
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    if payload.role is None and payload.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No updates provided.")
    if user.id == admin_user.id:
        if payload.is_active is False or payload.role == "user":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove your own admin access.",
            )
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.get("/stats/bookmakers")
def bookmaker_stats(db: Session = Depends(get_db)):
    bookmakers = db.execute(select(Bookmaker)).scalars().all()
    stats = []
    for bookmaker in bookmakers:
        odds_count = (
            db.execute(
                select(func.count(Odd.id)).where(Odd.bookmaker_id == bookmaker.id)
            )
            .scalar_one()
        )
        markets_count = (
            db.execute(
                select(func.count(func.distinct(Odd.market_id))).where(
                    Odd.bookmaker_id == bookmaker.id
                )
            )
            .scalar_one()
        )
        events_count = (
            db.execute(
                select(func.count(func.distinct(Market.event_id)))
                .select_from(Market)
                .join(Odd, Odd.market_id == Market.id)
                .where(Odd.bookmaker_id == bookmaker.id)
            )
            .scalar_one()
        )
        last_update = (
            db.execute(
                select(func.max(Odd.pulled_at)).where(
                    Odd.bookmaker_id == bookmaker.id
                )
            )
            .scalar_one()
        )
        stats.append(
            {
                "bookmaker": bookmaker.name,
                "bookmaker_id": bookmaker.id,
                "events": int(events_count or 0),
                "markets": int(markets_count or 0),
                "odds": int(odds_count or 0),
                "last_update": last_update.isoformat() if last_update else "",
            }
        )
    return stats


@router.get("/tasks")
def list_tasks():
    return {"tasks": sorted(TASKS.keys())}


@router.post("/tasks/run")
def run_task(name: str):
    if name not in TASKS:
        raise HTTPException(status_code=404, detail="unknown task")
    status = TASK_STATUS.get(name)
    if status and status.get("status") == "running":
        raise HTTPException(status_code=409, detail="task already running")
    script_path = ROOT_DIR / TASKS[name]
    if not script_path.exists():
        raise HTTPException(status_code=404, detail="script not found")
    process = subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    TASK_STATUS[name] = {
        "status": "running",
        "progress": 0.0,
        "step": "Starting...",
        "stdout": "",
        "stderr": "",
        "returncode": None,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": "",
    }
    threading.Thread(target=_track_process, args=(name, process), daemon=True).start()
    return {"status": "running"}


@router.get("/tasks/status")
def task_status(name: str):
    if name not in TASKS:
        raise HTTPException(status_code=404, detail="unknown task")
    status = TASK_STATUS.get(name)
    if not status:
        return {"status": "idle", "progress": 0.0, "step": ""}
    return status


@router.get("/settings/odds-api-bookmakers")
def get_odds_api_bookmakers():
    values = _read_env()
    return {"bookmakers": values.get("ODDS_API_BOOKMAKERS", "")}


@router.post("/settings/odds-api-bookmakers")
def set_odds_api_bookmakers(payload: dict):
    raw = (payload.get("bookmakers") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="bookmakers is required")
    parts = [b.strip() for b in raw.split(",") if b.strip()]
    if len(parts) > 2:
        raise HTTPException(status_code=400, detail="max 2 bookmakers on free plan")
    _write_env({"ODDS_API_BOOKMAKERS": ",".join(parts)})
    return {"bookmakers": ",".join(parts)}
