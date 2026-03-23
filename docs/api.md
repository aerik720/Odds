# API Endpoints (Sketch)

## Health
- GET /health

## Auth (placeholder)
- POST /auth/login
- POST /auth/logout
- GET /auth/me

## Events
- GET /events
- GET /events/{event_id}

## Markets
- GET /markets?event_id=

## Odds
- GET /odds?market_id=
- POST /admin/odds  # manual insert
- POST /admin/odds/import  # csv upload

## Surebets
- GET /surebets?min_edge_pct=&sport=&league=
- GET /surebets/{surebet_id}

## Admin
- POST /admin/events
- POST /admin/markets
- POST /admin/bookmakers
