"""Market structure, liquidity, POI, target and risk sub-engines.

Candle schema (normalized): dict with keys
    timestamp (iso str), open, high, low, close, volume
All detectors respect CLOSED candles only (no look-ahead): callers pass
the exact history that would have been visible at that point in time.
"""
from typing import List, Dict, Optional

Candle = Dict[str, float]

BULLISH = "BULLISH"
BEARISH = "BEARISH"
NEUTRAL = "NEUTRAL"


# ----------------------------- Market Structure -----------------------------
def find_swings(candles: List[Candle], k: int = 1) -> List[dict]:
    """Fractal swing highs/lows. A swing needs k strictly-lower/higher neighbours each side."""
    swings = []
    n = len(candles)
    for i in range(k, n - k):
        hi = candles[i]["high"]
        lo = candles[i]["low"]
        is_high = all(candles[j]["high"] < hi for j in range(i - k, i)) and \
                  all(candles[j]["high"] < hi for j in range(i + 1, i + k + 1))
        is_low = all(candles[j]["low"] > lo for j in range(i - k, i)) and \
                 all(candles[j]["low"] > lo for j in range(i + 1, i + k + 1))
        if is_high:
            swings.append({"index": i, "type": "high", "price": hi,
                           "timestamp": candles[i].get("timestamp")})
        if is_low:
            swings.append({"index": i, "type": "low", "price": lo,
                           "timestamp": candles[i].get("timestamp")})
    return swings


def trend_state(candles: List[Candle], k: int = 1) -> str:
    """Directional state from the last two swing highs & lows (HH/HL vs LH/LL)."""
    sw = find_swings(candles, k)
    highs = [s for s in sw if s["type"] == "high"]
    lows = [s for s in sw if s["type"] == "low"]
    if len(highs) < 2 or len(lows) < 2:
        return NEUTRAL
    hh = highs[-1]["price"] > highs[-2]["price"]
    hl = lows[-1]["price"] > lows[-2]["price"]
    lh = highs[-1]["price"] < highs[-2]["price"]
    ll = lows[-1]["price"] < lows[-2]["price"]
    if hh and hl:
        return BULLISH
    if lh and ll:
        return BEARISH
    return NEUTRAL


def detect_market_shift(candles: List[Candle], direction: str, k: int = 1) -> Optional[dict]:
    """CHOCH / internal market shift: latest close breaks the most recent opposing swing."""
    sw = find_swings(candles, k)
    if not candles:
        return None
    last_close = candles[-1]["close"]
    if direction == "bullish":
        highs = [s for s in sw if s["type"] == "high"]
        if not highs:
            return None
        ref = highs[-1]
        if last_close > ref["price"]:
            return {"type": "CHOCH", "direction": "bullish", "price": ref["price"],
                    "timestamp": candles[-1].get("timestamp"), "reference_index": ref["index"]}
    else:
        lows = [s for s in sw if s["type"] == "low"]
        if not lows:
            return None
        ref = lows[-1]
        if last_close < ref["price"]:
            return {"type": "CHOCH", "direction": "bearish", "price": ref["price"],
                    "timestamp": candles[-1].get("timestamp"), "reference_index": ref["index"]}
    return None


# ----------------------------- Liquidity -----------------------------
def detect_sweep(candles: List[Candle], side: str, k: int = 1) -> Optional[dict]:
    """Qualifying liquidity sweep: wick past a prior swing level then close back inside.

    side='sell' -> sell-side liquidity below a swing low is swept (bullish context).
    side='buy'  -> buy-side liquidity above a swing high is swept (bearish context).
    """
    sw = find_swings(candles, k)
    if side == "sell":
        for low in [s for s in sw if s["type"] == "low"]:
            for j in range(low["index"] + 1, len(candles)):
                c = candles[j]
                if c["low"] < low["price"] and c["close"] > low["price"]:
                    return {"side": "sell", "level": low["price"], "swept_index": j,
                            "timestamp": c.get("timestamp"), "label": "SELL-SIDE SWEEP"}
    else:
        for high in [s for s in sw if s["type"] == "high"]:
            for j in range(high["index"] + 1, len(candles)):
                c = candles[j]
                if c["high"] > high["price"] and c["close"] < high["price"]:
                    return {"side": "buy", "level": high["price"], "swept_index": j,
                            "timestamp": c.get("timestamp"), "label": "BUY-SIDE SWEEP"}
    return None


def equal_levels(candles: List[Candle], tolerance: float = 0.0005, k: int = 1) -> dict:
    sw = find_swings(candles, k)
    highs = [s["price"] for s in sw if s["type"] == "high"]
    lows = [s["price"] for s in sw if s["type"] == "low"]

    def _equal(vals):
        out = []
        for i in range(len(vals)):
            for j in range(i + 1, len(vals)):
                if abs(vals[i] - vals[j]) <= tolerance * max(1.0, abs(vals[i])):
                    out.append(round((vals[i] + vals[j]) / 2, 6))
        return out

    return {"equal_highs": _equal(highs), "equal_lows": _equal(lows)}


# ----------------------------- POI -----------------------------
def find_poi(candles: List[Candle], direction: str) -> Optional[dict]:
    """Most recent order-block style POI in the given direction.

    bullish: last down candle immediately followed by bullish displacement (close > OB high).
    bearish: last up candle immediately followed by bearish displacement (close < OB low).
    """
    for i in range(len(candles) - 2, 0, -1):
        c = candles[i]
        nxt = candles[i + 1]
        if direction == "bullish":
            if c["close"] < c["open"] and nxt["close"] > c["high"]:
                poi = {"type": "demand", "direction": "bullish", "high": c["high"],
                       "low": c["low"], "index": i, "created_at": c.get("timestamp")}
                return _annotate_poi(poi, candles, i, direction)
        else:
            if c["close"] > c["open"] and nxt["close"] < c["low"]:
                poi = {"type": "supply", "direction": "bearish", "high": c["high"],
                       "low": c["low"], "index": i, "created_at": c.get("timestamp")}
                return _annotate_poi(poi, candles, i, direction)
    return None


def _annotate_poi(poi: dict, candles: List[Candle], created_idx: int, direction: str) -> dict:
    retests = 0
    for j in range(created_idx + 2, len(candles)):
        c = candles[j]
        if c["low"] <= poi["high"] and c["high"] >= poi["low"]:
            retests += 1
    poi["retest_count"] = retests
    poi["fresh"] = retests == 0
    poi["mitigated"] = False
    poi["invalidated"] = False
    return poi


def poi_mitigated(poi: dict, exec_candles: List[Candle]) -> bool:
    """POI mitigation: execution-timeframe price interacts with the POI zone."""
    for c in exec_candles:
        if c["low"] <= poi["high"] and c["high"] >= poi["low"]:
            return True
    return False


# ----------------------------- Target -----------------------------
def structural_levels(htf_candles: List[Candle], entry: float, direction: str,
                      k: int = 1) -> List[float]:
    """All structural swing levels beyond entry, ordered nearest-first.

    bullish -> swing highs above entry ascending; bearish -> swing lows below entry descending.
    """
    sw = find_swings(htf_candles, k)
    if direction == "bullish":
        return sorted([s["price"] for s in sw if s["type"] == "high" and s["price"] > entry])
    return sorted([s["price"] for s in sw if s["type"] == "low" and s["price"] < entry],
                  reverse=True)


def structural_target(htf_candles: List[Candle], entry: float, stop: float,
                      direction: str, k: int = 1) -> Optional[dict]:
    """Nearest *meaningful* structural target: closest swing beyond entry giving RR >= MIN_RR.

    Targets too close to entry (structurally meaningless, RR < 2) are rejected.
    """
    risk = abs(entry - stop)
    if risk == 0:
        return None
    sw = find_swings(htf_candles, k)
    if direction == "bullish":
        candidates = sorted([s["price"] for s in sw if s["type"] == "high" and s["price"] > entry])
        for price in candidates:
            if (price - entry) / risk >= MIN_RR:
                return {"price": price, "kind": "structural_high"}
    else:
        candidates = sorted([s["price"] for s in sw if s["type"] == "low" and s["price"] < entry],
                            reverse=True)
        for price in candidates:
            if (entry - price) / risk >= MIN_RR:
                return {"price": price, "kind": "structural_low"}
    return None


# ----------------------------- Risk -----------------------------
MIN_RR = 2.0
MAX_RR = 5.0


def compute_risk(equity: float, risk_pct: float, entry: float, stop: float,
                 target: float, asset_class: str = "forex") -> dict:
    risk_per_unit = abs(entry - stop)
    reward_per_unit = abs(target - entry)
    if risk_per_unit == 0:
        return {"error": "Stop equals entry — invalid risk"}
    rr = round(reward_per_unit / risk_per_unit, 4)
    risk_amount = round(equity * risk_pct / 100.0, 2)
    position_size = round(risk_amount / risk_per_unit, 4)
    return {
        "equity": equity,
        "risk_pct": risk_pct,
        "risk_amount": risk_amount,
        "entry": round(entry, 6),
        "stop": round(stop, 6),
        "target": round(target, 6),
        "position_size": position_size,
        "rr": rr,
        "potential_profit": round(position_size * reward_per_unit, 2),
        "potential_loss": risk_amount,
        "rr_valid": MIN_RR <= rr <= MAX_RR,
        "asset_class": asset_class,
    }
