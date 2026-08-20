"""Deterministic golden & negative scenarios for the V4 validation suite.

The golden bullish fixture is hand-crafted so every V4 gate passes; the bearish
fixture is a price reflection of it (distances preserved -> identical RR). Negative
fixtures each break exactly one gate.
"""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from typing import List, Dict

_BASE = datetime(2020, 1, 6, 8, 0, tzinfo=timezone.utc)


def _c(o, h, l, c, i, step_min=5):
    return {
        "timestamp": (_BASE + timedelta(minutes=i * step_min)).isoformat(),
        "open": o, "high": h, "low": l, "close": c, "volume": 1000.0,
    }


def _mk(rows):
    return [_c(*r, i) for i, r in enumerate(rows)]


# ------------------- Golden BULLISH fixtures -------------------
def _bull_4h():
    path = [100, 104, 101, 106, 103, 109, 106, 112, 109, 115, 112, 118, 115]
    return _mk([(p, p + 1, p - 1, p) for p in path])


def _bull_1h():
    rows = [
        (100, 101, 99.5, 100.5),
        (100.5, 102, 100, 101.5),
        (101.5, 103, 101, 102.5),
        (102.5, 104, 102, 103.5),
        (103.5, 103.7, 101, 101.2),     # OB (bearish) -> POI high103.7 low101
        (103.9, 107, 103.8, 106.5),     # bullish displacement (leaves zone -> fresh)
        (106.5, 108, 106, 107.5),
        (107.5, 113, 107.4, 112),       # structural swing high 113
        (112, 112.5, 110, 111),
    ]
    return _mk(rows)


def _bull_15m():
    rows = [
        (100, 100.5, 99.5, 100),
        (100, 99.2, 96, 98),            # swing low 96
        (98, 100, 97.8, 99.5),          # swing high 100
        (99.5, 99.7, 95.5, 96.1),       # sweep of low 96 (low95.5<96, close96.1>96)
        (96.1, 96.5, 94.5, 96.2),
        (96.2, 100.2, 96, 99),
        (99, 101, 98.8, 100.8),         # close 100.8 > swing high 100 -> bullish CHOCH
    ]
    return _mk(rows)


def _bull_10m():
    rows = [
        (100, 100.5, 99.5, 100),
        (100, 99.2, 97, 98),
        (98, 99.5, 97.8, 99),           # swing high 99.5
        (99, 99.2, 96.5, 97),           # swing low
        (97, 100.5, 96.8, 100.2),       # close 100.2 > 99.5 -> bullish CHOCH
    ]
    return _mk(rows)


def _bull_5m():
    rows = [
        (105, 105.2, 104.5, 104.8),
        (104.8, 104.9, 102.5, 103),     # dips into POI zone [101,103.7] -> mitigated
        (103, 103.5, 102.8, 103.4),
    ]
    return _mk(rows)


def golden_bullish() -> Dict[str, List[dict]]:
    return {"4H": _bull_4h(), "1H": _bull_1h(), "15M": _bull_15m(),
            "10M": _bull_10m(), "5M": _bull_5m()}


# ------------------- Golden BEARISH (reflection) -------------------
def _reflect(candles, center=110.0):
    out = []
    for c in candles:
        d = dict(c)
        o = 2 * center - c["open"]
        cl = 2 * center - c["close"]
        hi = 2 * center - c["low"]
        lo = 2 * center - c["high"]
        d.update(open=o, close=cl, high=hi, low=lo)
        out.append(d)
    return out


def golden_bearish() -> Dict[str, List[dict]]:
    g = golden_bullish()
    return {tf: _reflect(candles) for tf, candles in g.items()}


# ------------------- Negative fixtures -------------------
def _flat_uptrend_1h():
    # monotonic rise -> no bearish OB candle -> no POI
    rows = [(100 + i, 100.5 + i, 99.8 + i, 100.4 + i) for i in range(9)]
    return _mk(rows)


def negatives() -> Dict[str, Dict[str, List[dict]]]:
    out = {}

    g = golden_bullish(); g["1H"] = _flat_uptrend_1h()
    out["NO_POI"] = g

    g = golden_bullish()
    g["15M"] = _mk([(100, 100.5, 99.5, 100), (100, 99.2, 96, 98),
                    (98, 100, 97.8, 99.5), (99.5, 99.7, 95.5, 96.1),
                    (96.1, 98.5, 96, 97), (97, 98, 96.5, 97.2)])  # never closes above swing high
    out["NO_15M_MARKET_SHIFT"] = g

    g = golden_bullish()
    g["15M"] = _mk([(100, 100.5, 99.0, 100), (100, 101, 98.0, 100.5),
                    (100.5, 101.5, 100, 101), (101, 101.2, 99.5, 99.8),
                    (99.8, 102.5, 99.6, 102)])  # CHOCH present but no wick below any prior low
    out["NO_FINAL_LIQUIDITY_SEQUENCE"] = g

    g = golden_bullish()
    g["10M"] = _mk([(100, 100.5, 99.5, 100), (100, 100.2, 97, 98),
                    (98, 99, 97.8, 98.5), (98.5, 99, 97.5, 98),
                    (98, 98.5, 97.2, 97.8)])  # never breaks up -> no confirmation
    out["NO_10M_MARKET_SHIFT"] = g

    g = golden_bullish()
    # 10M makes a BEARISH choch (wrong direction)
    g["10M"] = _mk([(100, 100.5, 99.5, 100), (100, 102, 99.8, 101.5),
                    (101.5, 102, 100.5, 101), (101, 101.5, 100.8, 101.2),
                    (101.2, 101.3, 98, 98.5)])  # close below swing low -> bearish
    out["10M_WRONG_DIRECTION"] = g

    g = golden_bullish()
    g["5M"] = _mk([(108, 108.5, 107.5, 108), (108, 108.2, 106, 106.5),
                   (106.5, 107, 105, 105.5)])  # stays above POI (top 103.7) -> not mitigated
    out["POI_NOT_MITIGATED"] = g

    return out
