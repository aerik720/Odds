# Data Model (Sketch)

## events
- id (uuid)
- sport (text)
- league (text)
- home_team (text)
- away_team (text)
- start_time (timestamptz)
- created_at (timestamptz)

## markets
- id (uuid)
- event_id (uuid, fk -> events.id)
- market_type (text)  # ex: 1X2, O/U, AH
- spec (text)         # ex: "O/U 2.5" or "AH -0.5"
- is_live (bool)
- created_at (timestamptz)

## bookmakers
- id (uuid)
- name (text)
- region (text)
- website (text)
- created_at (timestamptz)

## odds
- id (uuid)
- market_id (uuid, fk -> markets.id)
- bookmaker_id (uuid, fk -> bookmakers.id)
- outcome (text)      # ex: home, draw, away, over, under
- price_decimal (numeric)
- pulled_at (timestamptz)
- source (text)       # manual, csv, scraper, api

## surebet_snapshots
- id (uuid)
- event_id (uuid, fk -> events.id)
- market_id (uuid, fk -> markets.id)
- total_implied_prob (numeric)
- edge_pct (numeric)
- created_at (timestamptz)

## users
- id (uuid)
- email (text)
- role (text)         # admin, user
- created_at (timestamptz)

Notes:
- Implied probability per outcome = 1 / price_decimal.
- Surebet when sum(implied) < 1.
- Consider unique constraints on (market_id, bookmaker_id, outcome, pulled_at).
