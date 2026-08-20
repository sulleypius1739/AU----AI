# AUREUS AI — V4 A+ Market Mechanics Trading Platform

Institutional-style market-analysis, signal, backtesting, risk, journaling and research
platform built around **one high-conviction setup only** — the AUREUS V4 A+ strategy.

> **AUREUS does not trade often. AUREUS waits for the correct sequence.**

```
4H DIRECTION → 1H FRESH POI → 15M MARKET SHIFT → 15M LIQUIDITY SWEEP
→ 10M SAME-DIRECTION CONFIRMATION → POI MITIGATION → M5 EXECUTION → 2R–5R TARGET
```

The authoritative signal always comes from the validated Python backend engine. The
frontend never silently replaces the engine.

---

## Architecture

```
Frontend (React terminal)
      ↓  REST /api
FastAPI backend (server.py)
      ↓
AUREUS V4 engine (backend/aureus/*)
```

### Backend (`/app/backend`)
```
server.py                 FastAPI app, all /api routes
aureus/
  engine.py               market structure · liquidity · POI · target · risk
  strategy.py             V4 top-down orchestrator + signal states (hard-gate, no scoring)
  scenarios.py            golden bullish/bearish + negative fixtures
  data.py                 normalized OHLC · synthetic generator · MTF resampling · CSV
  backtest.py             walk-forward engine (no look-ahead) + metrics
  context.py              news calendar · news-risk gate · fundamentals · confluence
  ai.py                   AUREUS AI explanation (Emergent LLM, explains — never invents)
  auth.py                 JWT auth (email/password + president/trader roles)
  models.py               Pydantic models (PyObjectId / BaseDocument)
tests/test_strategy.py    MANDATORY golden + negative validation suite
```

### Frontend (`/app/frontend`)
TradingView-style white terminal (`src/App.js`): symbol search, watchlist, canvas
candlestick chart with AUREUS annotations (POI zone, entry/stop/target lines), timeframe
navigation, live tick, drawing-tool bar, signal panel, risk planner, news/fundamentals,
AI panel, backtest / journal / V4-validation / president dashboards.

`aureus_terminal.html` — portable single-file version of the terminal (per spec §39).

---

## Signal states
`WAIT · WATCH · ARMED · CONFIRMED · A+ BUY · A+ SELL · INVALIDATED · EXPIRED`
RR is hard-gated: `RR < 2R → REJECT`, `2R–5R → VALID`, `RR > 5R → REJECT`.

---

## Key API endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/candles?symbol=&timeframe=&limit=` | normalized OHLC (REAL-TIME/HISTORICAL) |
| GET | `/api/signal?symbol=` | authoritative V4 signal for live synthetic data |
| GET | `/api/signal/demo?direction=bullish\|bearish` | golden A+ demonstration |
| GET | `/api/topdown?symbol=` | per-timeframe top-down state |
| POST| `/api/risk` | position size / R:R / P&L |
| GET | `/api/backtest?symbol=&candles=` | walk-forward backtest + metrics |
| GET | `/api/validation` | run golden + negative suite |
| GET | `/api/news`, `/api/news/risk`, `/api/fundamentals`, `/api/confluence` | context |
| POST| `/api/ai/explain` | AUREUS AI explanation of a setup |
| GET | `/api/instruments?q=` | global market search |
| GET | `/api/watchlist` | quotes |
| *   | `/api/auth/*`, `/api/journal` | JWT auth + trade journal |
| GET | `/api/admin/status` | president/engine status dashboard |

---

## Run locally
```bash
# Backend
cd backend
cp .env.example .env          # then fill in secrets
pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# Validation suite (mandatory before releases)
python -m pytest tests/ -v

# Frontend
cd frontend
cp .env.example .env          # set REACT_APP_BACKEND_URL
yarn install
yarn start
```

---

## Data
Ships with a **deterministic synthetic OHLC generator** (seeded per symbol) so the whole
platform runs with no API key. Upload real history via `POST /api/upload-csv`, or plug a
market-data provider into `aureus/data.py` (every response normalizes to
`symbol, asset_class, exchange, timestamp, open, high, low, close, volume`).

## Security
No private keys in source. All secrets via `backend/.env` (`.env.example` documents them).
Auth is server-side JWT. The frontend only ever reads `REACT_APP_BACKEND_URL`.

## Honesty
No fake "coming soon" buttons. The AI panel labels itself `NOT CONNECTED` when
`EMERGENT_LLM_KEY` is absent and falls back to a rule-based explanation. News/fundamentals
are labelled reference/BETA (not a live feed).

## Default login
President/admin is seeded on startup from `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
