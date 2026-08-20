# AUREUS AI — PRD

## Problem statement
Institutional TradingView-style platform around the V4 A+ market-mechanics strategy
(4H direction → 1H fresh POI → 15M market shift → 15M liquidity sweep → 10M confirmation
→ POI mitigation → M5 execution → 2R–5R structural target). One high-conviction setup only.
Philosophy: "AUREUS does not trade often. AUREUS waits for the correct sequence."

## Stack / architecture
- Python FastAPI backend, React frontend, MongoDB. Frontend → /api → FastAPI → V4 engine.
- Backend modules: aureus/{engine,strategy,scenarios,data,backtest,context,ai,auth,models,providers}.py
- Auth: JWT (president + trader roles). AI: Emergent LLM (Claude). Data: Twelve Data provider
  with deterministic synthetic fallback (no key required).

## Implemented (2026-06)
- V4 engine: market structure, liquidity sweeps, POI, structural target, risk. Signal states
  WAIT/WATCH/ARMED/CONFIRMED/A+ BUY/A+ SELL/INVALIDATED. Golden + negative validation suite.
- TP placed a few pips beyond the nearest structural swing; stops padded beyond POI.
- O(n) walk-forward backtester (4Y feasible), trade management (BE + 50% partial at 1R),
  SL-before-TP diagnostics, matched A/B (TP@swing vs beyond), RR distribution, drawdown.
- 4-year report across 16 instruments (EUR/USD ~60% win rate; 50–70% across instruments).
  Data is SYNTHETIC and labelled as such.
- REST APIs: candles, signal, signal/demo, topdown, risk, backtest, backtest/report,
  validation, news, news/risk, fundamentals, confluence, ai/explain, instruments, watchlist,
  journal (CRUD), auth/*, admin/status.
- Terminal UI: canvas chart w/ POI+entry/stop/target annotations, symbol search, watchlist,
  timeframe nav, signal panel (7 checks + hypothetical-plan label), risk planner, news/
  fundamentals, AI panel, backtest report tab, journal, president dashboard, V4 validation tab.
- Alerts (browser + sound + banner) for A+ setups; candle-by-candle replay (no look-ahead).
- Live data provider (Twelve Data) with synthetic fallback + normalized schema.
- Packaged for GitHub: README, .env.example, .gitignore, portable aureus_terminal.html.

## Verified
- iteration_2: 49/49 (strategy + backtest + matched A/B). iteration_3: 78 pass / 2 fail
  (only pre-existing auth-hardening gaps). No critical/blocking defects.

## Backlog (P1/P2)
- P1: Activate live data (needs TWELVE_DATA_API_KEY); real 4Y needs paid data plan.
- P1: Auth hardening — brute-force lockout (5 fails) + explicit CORS origins.
- P2: Entry-trigger refinement (displacement/FVG) to raise win rate; TP buffer sweep (fraction of R).
- P2: Lower-dock height/scroll polish; equity/drawdown curve charts; multi-watchlists; drawing-tool persistence.

## Test credentials
president@aureus.ai / Aureus2020! (see /app/memory/test_credentials.md)
