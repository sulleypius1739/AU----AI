"""Generate the AUREUS V4 4-year backtest report and cache it to report.json.

Runs the full ~4-year window on the primary dataset (EUR/USD) in three modes so the
TP-beyond-swing adjustment and trade management can be compared, plus a lighter pass
across all tracked instruments.

DATA HONESTY: this uses the deterministic SYNTHETIC generator (no external key). Plug a
real OHLC provider into aureus/data.py for real-money-grade numbers.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aureus import data as D
from aureus import backtest as BT

OUT = Path(__file__).resolve().parents[1] / "aureus" / "report.json"
YEARS = 4
BARS_4Y = YEARS * 365 * 288          # ~4 years of 5M
BARS_INSTRUMENT = 288 * 365          # ~1 year for the multi-instrument sweep

INSTRUMENTS = ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "XAG/USD", "AAPL", "TSLA",
               "NVDA", "MSFT", "SPY", "QQQ", "BTC/USD", "ETH/USD", "US OIL", "GER40", "US30"]


def run():
    t0 = time.time()
    print("Generating 4Y EUR/USD ...", flush=True)
    base = D.generate_5m("EUR/USD", BARS_4Y)

    print("Backtest EUR/USD baseline (TP at swing)...", flush=True)
    before = BT.run_backtest(base, tp_mode="at", manage=False)
    print("Backtest EUR/USD adjusted (TP beyond swing)...", flush=True)
    after = BT.run_backtest(base, tp_mode="beyond", manage=False)
    print("Backtest EUR/USD managed (TP beyond + BE/partial)...", flush=True)
    managed = BT.run_backtest(base, tp_mode="beyond", manage=True)
    print("Matched A/B (same entries: TP at vs beyond)...", flush=True)
    matched = BT.run_ab_matched(base)
    del base

    per_instrument = []
    for sym in INSTRUMENTS:
        b = D.generate_5m(sym, BARS_INSTRUMENT)
        m = BT.run_backtest(b, tp_mode="beyond", manage=False)["metrics"]
        per_instrument.append({
            "symbol": sym, "trades": m.get("total_trades", 0),
            "win_rate": m.get("win_rate", 0), "profit_factor": m.get("profit_factor", 0),
            "net_r": m.get("net_r", 0), "max_drawdown_r": m.get("max_drawdown_r", 0),
        })
        print(f"  {sym}: n={m.get('total_trades')} win%={m.get('win_rate')}", flush=True)
        del b

    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "data_source": "SYNTHETIC (deterministic, seeded per symbol) — not live market data",
        "primary_dataset": "EUR/USD 5M",
        "window_years": YEARS,
        "bars_tested": BARS_4Y,
        "eurusd": {
            "before_tp_at_swing": before["metrics"],
            "after_tp_beyond_swing": after["metrics"],
            "after_with_management": managed["metrics"],
            "matched_ab": matched,
        },
        "per_instrument": per_instrument,
        "runtime_seconds": round(time.time() - t0, 1),
    }
    OUT.write_text(json.dumps(report))
    b1 = before["metrics"]; a1 = after["metrics"]; g1 = managed["metrics"]
    print("\n=== EUR/USD 4Y ===")
    print(f"before (TP at swing):     win% {b1.get('win_rate')}  PF {b1.get('profit_factor')}  "
          f"SL-then-TP {b1.get('sl_hit_then_tp_would_fill')}/{b1.get('sl_before_tp_count')}")
    print(f"after  (TP beyond swing): win% {a1.get('win_rate')}  PF {a1.get('profit_factor')}  "
          f"SL-then-TP {a1.get('sl_hit_then_tp_would_fill')}/{a1.get('sl_before_tp_count')}")
    print(f"after + management:       win% {g1.get('win_rate')}  PF {g1.get('profit_factor')}")
    print(f"Saved -> {OUT}  ({report['runtime_seconds']}s)")


if __name__ == "__main__":
    run()
