"""Backtesting engine + metrics. Walk-forward, closed-candle only, no look-ahead.

Efficient: the multi-timeframe set is resampled ONCE up-front, then each step slices
each timeframe by closed-candle time (bisect). This makes multi-year 5M backtests feasible.

Trade management (optional): at +1R, bank a 50% partial and move the stop to break-even.
Every stop-out is flagged, and we detect "SL hit before TP but TP would have filled after"
(premature stop-out) so the target placement can be evaluated.
"""
import bisect
from datetime import datetime
from typing import List, Dict
from . import data as D
from . import strategy as S

LOOKBACK = {"5M": 80, "10M": 150, "15M": 150, "1H": 140, "4H": 80, "1D": 40}


def _close_epochs(series: List[Dict], tf: str) -> List[float]:
    dur = D.TF_MINUTES[tf] * 60
    return [datetime.fromisoformat(c["timestamp"]).timestamp() + dur for c in series]


def run_backtest(candles_5m: List[Dict], equity: float = 10000.0, risk_pct: float = 1.0,
                 step: int = 12, warmup: int = 600, slippage: float = 0.0,
                 max_hold: int = 288, tp_mode: str = "beyond", manage: bool = True) -> dict:
    n = len(candles_5m)
    if n < warmup + 10:
        return {"trades": [], "metrics": compute_metrics([]), "config": _cfg(tp_mode, manage)}
    symbol = candles_5m[0]["symbol"]
    pip = D.pip_size(symbol)
    mtf = D.multi_timeframe(candles_5m)
    meta = {tf: (series, _close_epochs(series, tf)) for tf, series in mtf.items()}
    base_close = meta["5M"][1]

    trades = []
    i = warmup
    while i < n - 1:
        t = base_close[i]
        tf_data = {}
        for tf, (series, ce) in meta.items():
            idx = bisect.bisect_right(ce, t)
            tf_data[tf] = series[max(0, idx - LOOKBACK[tf]):idx]
        sig = S.build_signal(tf_data, symbol=symbol, equity=equity, risk_pct=risk_pct,
                             pip=pip, tp_mode=tp_mode)
        if sig["actionable"] and sig["trade_plan"]:
            p = sig["trade_plan"]
            direction = sig["direction"]
            entry = p["entry"] + (slippage if direction == "bullish" else -slippage)
            out = _simulate(candles_5m, i + 1, direction, entry, p["stop"], p["target"],
                            max_hold, manage)
            trades.append({
                "index": i, "direction": direction, "entry": round(entry, 6),
                "stop": p["stop"], "target": p["target"], "target_swing": p.get("target_swing"),
                "rr_planned": p["rr"], "tp_mode": p.get("tp_mode"),
                "result": out["result"], "r_result": out["r"],
                "entry_time": candles_5m[i + 1]["timestamp"], "exit_time": out["exit_time"],
                "reason": out["reason"], "sl_before_tp": out["sl_before_tp"],
                "recovered_after_sl": out["recovered"],
                "market_context": f"4H {direction} / V4 A+",
            })
            i += out["bars"] + step               # cooldown / one-time POI usage
        else:
            i += step
    return {"trades": trades, "metrics": compute_metrics(trades), "config": _cfg(tp_mode, manage)}


def run_ab_matched(candles_5m: List[Dict], step: int = 12, warmup: int = 600,
                   max_hold: int = 288) -> dict:
    """Evaluate TP@swing vs TP-beyond-swing on the SAME entry set (management off).

    A trade enters the matched set only when BOTH modes yield a valid 2R-5R target, so the
    before/after win-rate and SL-before-TP breakdown is an apples-to-apples comparison.
    """
    n = len(candles_5m)
    if n < warmup + 10:
        return {"matched_trades": 0}
    symbol = candles_5m[0]["symbol"]
    pip = D.pip_size(symbol)
    mtf = D.multi_timeframe(candles_5m)
    meta = {tf: (series, _close_epochs(series, tf)) for tf, series in mtf.items()}
    base_close = meta["5M"][1]
    at_tr, beyond_tr = [], []
    i = warmup
    while i < n - 1:
        t = base_close[i]
        tf_data = {tf: series[max(0, bisect.bisect_right(ce, t) - LOOKBACK[tf]):bisect.bisect_right(ce, t)]
                   for tf, (series, ce) in meta.items()}
        ctx = S.entry_setup(tf_data, pip)
        if ctx:
            ta = S.target_for(ctx, "at", pip)
            tb = S.target_for(ctx, "beyond", pip)
            if ta and tb:
                oa = _simulate(candles_5m, i + 1, ctx["direction"], ctx["entry"], ctx["stop"], ta["target"], max_hold, False)
                ob = _simulate(candles_5m, i + 1, ctx["direction"], ctx["entry"], ctx["stop"], tb["target"], max_hold, False)
                at_tr.append({"direction": ctx["direction"], "result": oa["result"], "r_result": oa["r"],
                              "sl_before_tp": oa["sl_before_tp"], "recovered_after_sl": oa["recovered"], "rr_planned": ta["rr"]})
                beyond_tr.append({"direction": ctx["direction"], "result": ob["result"], "r_result": ob["r"],
                                  "sl_before_tp": ob["sl_before_tp"], "recovered_after_sl": ob["recovered"], "rr_planned": tb["rr"]})
                i += max(oa["bars"], ob["bars"]) + step
                continue
        i += step
    return {"matched_trades": len(at_tr),
            "tp_at_swing": compute_metrics(at_tr),
            "tp_beyond_swing": compute_metrics(beyond_tr)}


def _cfg(tp_mode, manage):
    return {"tp_mode": tp_mode, "management": manage,
            "management_rule": "BE + 50% partial at +1R" if manage else "none"}


def _simulate(candles, start, direction, entry, stop, target, max_hold, manage):
    end = min(start + max_hold, len(candles))
    risk = abs(entry - stop)
    if risk == 0:
        return _exit("breakeven", 0.0, candles[start], 1, "Invalid risk", False, False)
    r1 = entry + risk * (1 if direction == "bullish" else -1)   # +1R level
    banked, remaining, cur_stop, moved = 0.0, 1.0, stop, False

    for k in range(start, end):
        c = candles[k]
        if direction == "bullish":
            if c["low"] <= cur_stop:
                r = banked + remaining * ((cur_stop - entry) / risk)
                rec = _recover(candles, k + 1, end, target, "bullish")
                return _exit(_res(r), r, c, k - start, "Stop hit", not moved, rec)
            if manage and not moved and c["high"] >= r1:
                banked += 0.5 * 1.0
                remaining -= 0.5
                cur_stop = entry
                moved = True
            if c["high"] >= target:
                r = banked + remaining * ((target - entry) / risk)
                return _exit(_res(r), r, c, k - start, "Target hit", False, False)
        else:
            if c["high"] >= cur_stop:
                r = banked + remaining * ((entry - cur_stop) / risk)
                rec = _recover(candles, k + 1, end, target, "bearish")
                return _exit(_res(r), r, c, k - start, "Stop hit", not moved, rec)
            if manage and not moved and c["low"] <= r1:
                banked += 0.5 * 1.0
                remaining -= 0.5
                cur_stop = entry
                moved = True
            if c["low"] <= target:
                r = banked + remaining * ((entry - target) / risk)
                return _exit(_res(r), r, c, k - start, "Target hit", False, False)

    c = candles[end - 1]
    return _exit(_res(banked), banked, c, end - start, "Max hold reached", False, False)


def _recover(candles, a, b, target, direction):
    """Would TP have filled after the stop was hit (within the horizon)?"""
    for j in range(a, b):
        if direction == "bullish" and candles[j]["high"] >= target:
            return True
        if direction == "bearish" and candles[j]["low"] <= target:
            return True
    return False


def _res(r):
    if r > 1e-9:
        return "win"
    if r < -1e-9:
        return "loss"
    return "breakeven"


def _exit(result, r, candle, bars, reason, sl_before_tp, recovered):
    return {"result": result, "r": round(r, 4), "exit_time": candle["timestamp"],
            "bars": max(bars, 1), "reason": reason,
            "sl_before_tp": sl_before_tp, "recovered": recovered}


def _rr_distribution(rs: List[float]) -> dict:
    buckets = {"<-1R": 0, "-1R..0": 0, "0..1R": 0, "1R..2R": 0, "2R..3R": 0, "3R..5R": 0, ">5R": 0}
    for r in rs:
        if r < -1:
            buckets["<-1R"] += 1
        elif r < 0:
            buckets["-1R..0"] += 1
        elif r < 1:
            buckets["0..1R"] += 1
        elif r < 2:
            buckets["1R..2R"] += 1
        elif r < 3:
            buckets["2R..3R"] += 1
        elif r <= 5:
            buckets["3R..5R"] += 1
        else:
            buckets[">5R"] += 1
    return buckets


def compute_metrics(trades: List[Dict], equity: float = 10000.0) -> dict:
    n = len(trades)
    if n == 0:
        return {"total_trades": 0,
                "note": "No A+ setups triggered in this window (by design, AUREUS waits)."}
    wins = [t for t in trades if t["result"] == "win"]
    losses = [t for t in trades if t["result"] == "loss"]
    rs = [t["r_result"] for t in trades]
    gross_win = sum(t["r_result"] for t in wins) or 1e-9
    gross_loss = abs(sum(t["r_result"] for t in losses)) or 1e-9
    equity_curve, dd_curve, cum, peak, max_dd = [], [], 0.0, 0.0, 0.0
    for t in trades:
        cum += t["r_result"]
        equity_curve.append(round(cum, 4))
        peak = max(peak, cum)
        max_dd = min(max_dd, cum - peak)
        dd_curve.append(round(cum - peak, 4))
    longs = [t for t in trades if t["direction"] == "bullish"]
    shorts = [t for t in trades if t["direction"] == "bearish"]
    sl_before_tp = [t for t in trades if t.get("sl_before_tp")]
    premature = [t for t in sl_before_tp if t.get("recovered_after_sl")]
    return {
        "total_trades": n,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / n * 100, 2),
        "profit_factor": round(min(gross_win / gross_loss, 999.0), 3),
        "net_r": round(sum(rs), 3),
        "average_r": round(sum(rs) / n, 3),
        "expectancy": round(sum(rs) / n, 3),
        "max_drawdown_r": round(max_dd, 3),
        "best_trade_r": round(max(rs), 3),
        "worst_trade_r": round(min(rs), 3),
        "long_trades": len(longs),
        "short_trades": len(shorts),
        "long_win_rate": round(len([t for t in longs if t["result"] == "win"]) / len(longs) * 100, 2) if longs else 0,
        "short_win_rate": round(len([t for t in shorts if t["result"] == "win"]) / len(shorts) * 100, 2) if shorts else 0,
        "a_plus_count": n,
        "sl_before_tp_count": len(sl_before_tp),
        "sl_hit_then_tp_would_fill": len(premature),
        "rr_distribution": _rr_distribution(rs),
        "equity_curve": equity_curve[:500],
        "drawdown_curve": dd_curve[:500],
    }
