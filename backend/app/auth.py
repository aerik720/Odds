from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from .db import get_db, _load_env_value
from .models import User

SECRET_KEY = _load_env_value("JWT_SECRET") or "dev-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(_load_env_value("JWT_EXPIRE_MINUTES") or "720")
ADMIN_EMAIL = _load_env_value("ADMIN_EMAIL")
ADMIN_PASSWORD = _load_env_value("ADMIN_PASSWORD")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    if password is None:
        raise ValueError("Password is required")
    raw = password.encode("utf-8")
    if len(raw) > 72:
        # bcrypt only uses first 72 bytes; pre-hash to keep long secrets usable
        raw = sha256(raw).hexdigest().encode("utf-8")
    return pwd_context.hash(raw.decode("utf-8"))


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise credentials_error
    except JWTError as exc:
        raise credentials_error from exc
    user = get_user_by_email(db, email)
    if not user or not user.is_active:
        raise credentials_error
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required.",
        )
    return user


def ensure_admin_user(db: Session) -> None:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    user = get_user_by_email(db, ADMIN_EMAIL)
    if user:
        if user.role != "admin":
            user.role = "admin"
            db.commit()
        if not user.password_hash:
            user.password_hash = hash_password(ADMIN_PASSWORD)
            db.commit()
        return
    admin = User(
        email=ADMIN_EMAIL,
        role="admin",
        password_hash=hash_password(ADMIN_PASSWORD),
        is_active=True,
    )
    db.add(admin)
    db.commit()
