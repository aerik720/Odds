from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    sport: str = Field(min_length=1, max_length=100)
    league: str = Field(min_length=1, max_length=200)
    home_team: str = Field(min_length=1, max_length=200)
    away_team: str = Field(min_length=1, max_length=200)
    start_time: datetime


class MarketCreate(BaseModel):
    event_id: str
    market_type: str = Field(min_length=1, max_length=50)
    spec: str = Field(min_length=1, max_length=100)
    is_live: bool = False


class BookmakerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    region: str = Field(min_length=1, max_length=80)
    website: str | None = Field(default=None, max_length=200)


class UpsertResponse(BaseModel):
    id: str
    created: bool


class EventAliasCreate(BaseModel):
    bookmaker_id: str
    event_id: str
    external_event_id: str = Field(min_length=1, max_length=200)


class MarketAliasCreate(BaseModel):
    bookmaker_id: str
    market_id: str
    external_market_id: str = Field(min_length=1, max_length=200)


class OddCreate(BaseModel):
    market_id: str
    bookmaker_id: str
    outcome: str = Field(min_length=1, max_length=50)
    side: str = Field(default="back", pattern="^(back|lay)$")
    price_decimal: Decimal = Field(gt=1)
    pulled_at: datetime
    source: str = Field(min_length=1, max_length=30)


class OddBatchCreate(BaseModel):
    items: list[OddCreate]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class UserOut(BaseModel):
    id: str
    email: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminUserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="user", pattern="^(user|admin)$")


class AdminUserUpdate(BaseModel):
    role: str | None = Field(default=None, pattern="^(user|admin)$")
    is_active: bool | None = None


class AdminUserOut(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class BetBase(BaseModel):
    external_key: str = Field(min_length=1, max_length=200)
    event_id: str | None = None
    source: str = Field(min_length=1, max_length=30)
    event: str = Field(min_length=1, max_length=200)
    market: str = Field(min_length=1, max_length=200)
    outcome: str = Field(min_length=1, max_length=100)
    stake: Decimal = Field(gt=0)
    payout: Decimal = Field(ge=0)
    profit: Decimal
    event_start_time: datetime | None = None
    placed_at: datetime | None = None


class BetCreate(BetBase):
    pass


class BetOut(BetBase):
    id: str
    odds_decimal: Decimal | None = None
    result: str = "pending"
    placed_at: datetime
    created_at: datetime


class BetUpdate(BaseModel):
    odds_decimal: Decimal | None = None
    result: str | None = Field(default=None, pattern="^(pending|win|loss|void)$")
