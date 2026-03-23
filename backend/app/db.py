import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

def _load_env_value(name: str) -> str | None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, val = line.partition("=")
            if sep != "=":
                continue
            if key.strip() == name:
                return val.strip().strip('"')
    value = os.getenv(name)
    if value:
        return value
    return None


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_PATH = (BASE_DIR / "app.db").resolve()
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"
DATABASE_URL = _load_env_value("DATABASE_URL") or DEFAULT_DATABASE_URL
if DATABASE_URL.startswith("sqlite:///./") or DATABASE_URL.startswith("sqlite:///\\."):
    DATABASE_URL = DEFAULT_DATABASE_URL
print(f"[db] Using DATABASE_URL={DATABASE_URL}")


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
