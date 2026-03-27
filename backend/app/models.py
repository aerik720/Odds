from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sport: Mapped[str] = mapped_column(String(100), nullable=False)
    league: Mapped[str] = mapped_column(String(200), nullable=False)
    home_team: Mapped[str] = mapped_column(String(200), nullable=False)
    away_team: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    markets: Mapped[list["Market"]] = relationship(back_populates="event")


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), nullable=False)
    market_type: Mapped[str] = mapped_column(String(50), nullable=False)
    spec: Mapped[str] = mapped_column(String(100), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped[Event] = relationship(back_populates="markets")
    odds: Mapped[list["Odd"]] = relationship(back_populates="market")

    __table_args__ = (UniqueConstraint("event_id", "market_type", "spec", "is_live"),)


class Bookmaker(Base):
    __tablename__ = "bookmakers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    website: Mapped[str] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    odds: Mapped[list["Odd"]] = relationship(back_populates="bookmaker")


class Odd(Base):
    __tablename__ = "odds"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    bookmaker_id: Mapped[str] = mapped_column(String(36), ForeignKey("bookmakers.id"), nullable=False)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    side: Mapped[str] = mapped_column(String(10), nullable=False, default="back", server_default="back")
    price_decimal: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    pulled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)

    market: Mapped[Market] = relationship(back_populates="odds")
    bookmaker: Mapped[Bookmaker] = relationship(back_populates="odds")

    __table_args__ = (
        UniqueConstraint("market_id", "bookmaker_id", "outcome", "side", "pulled_at"),
    )


class SurebetSnapshot(Base):
    __tablename__ = "surebet_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    total_implied_prob: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    edge_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EventAlias(Base):
    __tablename__ = "event_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bookmaker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookmakers.id"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(36), ForeignKey("events.id"), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("bookmaker_id", "external_event_id"),)


class MarketAlias(Base):
    __tablename__ = "market_aliases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    bookmaker_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookmakers.id"), nullable=False
    )
    market_id: Mapped[str] = mapped_column(String(36), ForeignKey("markets.id"), nullable=False)
    external_market_id: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("bookmaker_id", "external_market_id"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    password_hash: Mapped[str] = mapped_column(
        String(200), nullable=False, server_default=""
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    bets: Mapped[list["Bet"]] = relationship(back_populates="user")


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    external_key: Mapped[str] = mapped_column(String(200), nullable=False)
    event_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    event: Mapped[str] = mapped_column(String(200), nullable=False)
    market: Mapped[str] = mapped_column(String(200), nullable=False)
    outcome: Mapped[str] = mapped_column(String(100), nullable=False)
    stake: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    profit: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    odds_decimal: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    result: Mapped[str] = mapped_column(String(10), nullable=False, server_default="pending")
    event_start_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="bets")

    __table_args__ = (UniqueConstraint("user_id", "external_key"),)
