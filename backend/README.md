# Backend

FastAPI placeholder.

## Database
Models live in `app/models.py`. Configure `DATABASE_URL` in `app/db.py`.

## Migrations
From `backend/`:
- `alembic revision --autogenerate -m "init"`
- `alembic upgrade head`

## Seed
From `backend/` after migrations:
- `python -m scripts.seed`

## Bootstrap via API
With API running:
- `python -m scripts.bootstrap_api`

## Admin endpoints
- POST `/admin/events`
- POST `/admin/events/upsert`
- POST `/admin/markets`
- POST `/admin/markets/upsert`
- POST `/admin/bookmakers`
- POST `/admin/bookmakers/upsert`
- POST `/admin/odds/batch`

## Odds API fetch
With API running:
- `python -m scripts.fetch_odds_api --max-events 50 --max-odds-requests 80`

## Odds API arbitrage
With API running:
- `python -m scripts.fetch_odds_api_arbitrage --limit 50`

## Arbitrage
- `GET /arbitrage/back-lay?commission=0.02`

## Run
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
