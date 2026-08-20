"""AUREUS V4 A+ top-down strategy orchestrator.

ONE HIGH-CONVICTION SETUP ONLY. Hard-gate sequence, no scoring:

  4H DIRECTION -> 1H FRESH POI -> 15M MARKET SHIFT -> 15M LIQUIDITY SWEEP
  -> 10M SAME-DIRECTION CONFIRMATION -> POI MITIGATION -> M5 EXECUTION -> 2R-5R
"""
from typing import Dict, List, Optional
from . import engine as E

# Signal states
WAIT = "WAIT"
WATCH = "WATCH"
ARMED = "ARMED"
CONFIRMED = "CONFIRMED"
A_PLUS_BUY = "A+ BUY"
A_PLUS_SELL = "A+ SELL"
INVALIDATED = "INVALIDATED"
EXPIRED = "EXPIRED"

STOP_PIPS, TP_PIPS = 2.0, 3.0


def entry_setup(tf_data: Dict[str, List[dict]], pip: float = 0.0):
    """Return the V4 entry context if all gates THROUGH POI mitigation pass, else None.

    Shared by build_signal and the matched A/B backtest so target-mode comparisons use
    an identical entry set. Does NOT decide RR/target — that is target-mode specific.
    """
    c4h, c1h = tf_data.get("4H", []), tf_data.get("1H", [])
    c15, c10, c5 = tf_data.get("15M", []), tf_data.get("10M", []), tf_data.get("5M", [])
    htf = E.trend_state(c4h)
    if htf == E.NEUTRAL:
        return None
    direction = "bullish" if htf == E.BULLISH else "bearish"
    poi = E.find_poi(c1h, direction)
    if not poi or not poi.get("fresh"):
        return None
    if E.detect_market_shift(c15, direction) is None:
        return None
    if E.detect_sweep(c15, "sell" if direction == "bullish" else "buy") is None:
        return None
    confirm = E.detect_market_shift(c10, direction)
    wrong = E.detect_market_shift(c10, "bearish" if direction == "bullish" else "bullish")
    if confirm is None or wrong is not None:
        return None
    if not E.poi_mitigated(poi, c5):
        return None
    if direction == "bullish":
        entry, stop = poi["high"], poi["low"] - pip * STOP_PIPS
        levels = E.structural_levels(c1h, entry, "bullish")
    else:
        entry, stop = poi["low"], poi["high"] + pip * STOP_PIPS
        levels = E.structural_levels(c1h, entry, "bearish")
    return {"direction": direction, "entry": entry, "stop": stop, "levels": levels}


def target_for(ctx: dict, tp_mode: str, pip: float = 0.0):
    """Nearest structural target for a mode giving RR in [2,5]. Returns (target, rr) or None."""
    tp_buf = pip * TP_PIPS
    entry, stop, direction = ctx["entry"], ctx["stop"], ctx["direction"]
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    for swing in ctx["levels"]:
        if direction == "bullish":
            target = swing + tp_buf if tp_mode == "beyond" else swing - tp_buf
            rr = (target - entry) / risk
        else:
            target = swing - tp_buf if tp_mode == "beyond" else swing + tp_buf
            rr = (entry - target) / risk
        if rr < E.MIN_RR:
            continue
        if rr <= E.MAX_RR:
            return {"target": round(target, 6), "rr": round(rr, 4), "swing": round(swing, 6)}
        return None
    return None


def _check(passed: bool, detail: str) -> dict:
    return {"passed": bool(passed), "detail": detail}


def build_signal(tf_data: Dict[str, List[dict]], symbol: str = "UNKNOWN",
                 equity: float = 10000.0, risk_pct: float = 1.0,
                 pip: float = 0.0, tp_mode: str = "beyond") -> dict:
    """Run the full V4 gate. tf_data must include 4H, 1H, 15M, 10M, 5M candle lists.

    tp_mode='beyond' places the target a few pips CLEAR of the nearest structural swing
    (above the high for longs, below the low for shorts) so TP sits past the liquidity
    zone rather than inside it. tp_mode='at' targets the raw swing (baseline).
    """
    c4h = tf_data.get("4H", [])
    c1h = tf_data.get("1H", [])
    c15 = tf_data.get("15M", [])
    c10 = tf_data.get("10M", [])
    c5 = tf_data.get("5M", [])

    # Step 1 — 4H direction
    htf_dir = E.trend_state(c4h)
    if htf_dir == E.NEUTRAL:
        empty = {k: _check(False, d) for k, d in [
            ("htf_direction", "4H direction is NEUTRAL"),
            ("poi", "Awaiting 4H direction"),
            ("market_shift", "Awaiting 4H direction"),
            ("liquidity_sweep", "Awaiting 4H direction"),
            ("ltf_confirmation", "Awaiting 4H direction"),
            ("poi_mitigation", "Awaiting 4H direction"),
            ("rr", "Awaiting 4H direction"),
        ]}
        return _result(symbol, "neutral", WAIT, empty,
                       missing="4H must be clearly BULLISH or BEARISH")

    direction = "bullish" if htf_dir == E.BULLISH else "bearish"
    sweep_side = "sell" if direction == "bullish" else "buy"
    checks = {"htf_direction": _check(True, f"4H {htf_dir}")}

    # Step 2 — fresh 1H POI
    poi = E.find_poi(c1h, direction)
    poi_ok = poi is not None and poi.get("fresh", False)
    checks["poi"] = _check(poi_ok,
                           f"Fresh {direction} POI [{poi['low']:.5f}-{poi['high']:.5f}]"
                           if poi else "No fresh 1H POI")

    # Step 3 — 15M market shift
    shift = E.detect_market_shift(c15, direction)
    checks["market_shift"] = _check(shift is not None,
                                    "15M CHOCH / MARKET SHIFT" if shift else "No 15M market shift")

    # Step 4 — 15M liquidity sweep
    sweep = E.detect_sweep(c15, sweep_side)
    checks["liquidity_sweep"] = _check(sweep is not None,
                                       sweep["label"] if sweep else f"No {sweep_side}-side sweep")

    # Step 5 — 10M same-direction confirmation
    confirm = E.detect_market_shift(c10, direction)
    wrong_10m = E.detect_market_shift(c10, "bearish" if direction == "bullish" else "bullish")
    confirm_ok = confirm is not None and wrong_10m is None
    checks["ltf_confirmation"] = _check(confirm_ok,
                                        f"10M {direction} confirmation" if confirm_ok
                                        else "No valid 10M confirmation")

    # Step 6 — POI mitigation
    mitig = bool(poi) and E.poi_mitigated(poi, c5)
    checks["poi_mitigation"] = _check(mitig, "POI mitigated on M5" if mitig else "POI not mitigated")

    # Step 7 — M5 execution + RR (TP placed a few pips beyond the liquidity swing)
    trade_plan = None
    rr_ok = False
    if poi and mitig:
        stop_buf = pip * STOP_PIPS
        tp_buf = pip * TP_PIPS
        if direction == "bullish":
            entry = poi["high"]
            stop = poi["low"] - stop_buf
            levels = E.structural_levels(c1h, entry, "bullish")
        else:
            entry = poi["low"]
            stop = poi["high"] + stop_buf
            levels = E.structural_levels(c1h, entry, "bearish")
        risk = abs(entry - stop)
        for swing in levels:
            if risk <= 0:
                break
            if direction == "bullish":
                target = swing + tp_buf if tp_mode == "beyond" else swing - tp_buf
                reward = target - entry
            else:
                target = swing - tp_buf if tp_mode == "beyond" else swing + tp_buf
                reward = entry - target
            rr = reward / risk
            if rr < E.MIN_RR:
                continue                      # too close / structurally meaningless
            plan = E.compute_risk(equity, risk_pct, entry, stop, target, "forex")
            plan["target_swing"] = round(swing, 6)
            plan["tp_mode"] = tp_mode
            plan["management"] = {"breakeven_at_r": 1.0, "partial_pct": 50,
                                  "note": "Bank 50% and move stop to break-even at +1R"}
            rr_ok = plan.get("rr_valid", False)
            trade_plan = plan
            break
    checks["rr"] = _check(rr_ok,
                          f"{trade_plan['rr']}R · TP {trade_plan['tp_mode']} swing"
                          if trade_plan
                          else "No structural target / RR out of range")

    status, missing = _resolve_status(direction, checks, trade_plan)
    return _result(symbol, direction, status, checks, trade_plan=trade_plan,
                   poi=poi, shift=shift, sweep=sweep, confirm=confirm, missing=missing)


def _resolve_status(direction, checks, trade_plan):
    seq = ["htf_direction", "poi", "market_shift", "liquidity_sweep",
           "ltf_confirmation", "poi_mitigation", "rr"]
    if not checks["htf_direction"]["passed"]:
        return WAIT, "4H not aligned"
    if not checks["poi"]["passed"]:
        return WAIT, "No fresh 1H POI"
    # POI present: WATCH until shift+sweep
    if not (checks["market_shift"]["passed"] and checks["liquidity_sweep"]["passed"]):
        return WATCH, "Awaiting 15M market shift + liquidity sweep"
    if not checks["ltf_confirmation"]["passed"]:
        return ARMED, "Awaiting 10M same-direction confirmation"
    if not checks["poi_mitigation"]["passed"]:
        return CONFIRMED, "Awaiting POI mitigation on M5"
    # All structure aligned — RR decides
    if trade_plan and checks["rr"]["passed"]:
        return (A_PLUS_BUY if direction == "bullish" else A_PLUS_SELL), None
    return INVALIDATED, "RR outside 2R-5R band"


def _result(symbol, direction, status, checks, trade_plan=None, missing=None,
            poi=None, shift=None, sweep=None, confirm=None):
    return {
        "symbol": symbol,
        "direction": direction,
        "status": status,
        "checks": checks,
        "trade_plan": trade_plan,
        "poi": poi,
        "events": {"market_shift": shift, "liquidity_sweep": sweep, "confirmation": confirm},
        "missing": missing,
        "actionable": status in (A_PLUS_BUY, A_PLUS_SELL),
        "philosophy": "AUREUS does not trade often. AUREUS waits for the correct sequence.",
    }
