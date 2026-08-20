"""Data layer: normalized OHLC, deterministic synthetic generation, MTF resampling, CSV.

Every provider/generator output is normalized to the common schema:
    symbol, asset_class, exchange, timestamp, open, high, low, close, volume
The engine can then work on any instrument without being rewritten.
"""
import hashlib
import io
from datetime import datetime, timezone, timedelta
from typing import List, Dict
import numpy as np
import pandas as pd

TF_MINUTES = {"1m": 1, "5M": 5, "10M": 10, "15M": 15, "30m": 30,
              "1H": 60, "2H": 120, "4H": 240, "1D": 1440}

PANDAS_RULE = {"5M": "5min", "10M": "10min", "15M": "15min", "30m": "30min",
               "1H": "60min", "2H": "120min", "4H": "240min", "1D": "1D"}


def _seed(symbol: str) -> int:
    return int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % (2**32)


def _base_price(symbol: str) -> float:
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:
        return 2000.0
    if "XAG" in s or "SILVER" in s:
        return 25.0
    if "BTC" in s:
        return 60000.0
    if "ETH" in s:
        return 3000.0
    if "JPY" in s:
        return 150.0
    if "/" in s or any(c in s for c in ["EUR", "GBP", "USD", "AUD", "NZD", "CAD", "CHF"]):
        return 1.1
    return 150.0  # equities/index default


def pip_size(symbol: str) -> float:
    s = symbol.upper()
    if "JPY" in s:
        return 0.01
    if "XAU" in s or "GOLD" in s:
        return 0.1
    if "XAG" in s or "SILVER" in s:
        return 0.01
    if "BTC" in s:
        return 1.0
    if "ETH" in s:
        return 0.1
    if "/" in s:
        return 0.0001
    return 0.01  # equities / indices


def generate_5m(symbol: str, count: int = 2000, end: datetime = None) -> List[Dict]:
    """Deterministic 5M candles with persistent trend regimes (seeded by symbol).

    A regime drift persists in blocks so the market actually trends/ranges — this gives
    the trend-aligned V4 A+ setups a genuine, testable edge (not a pure random walk).
    """
    end = end or datetime.now(timezone.utc)
    rng = np.random.default_rng(_seed(symbol))
    p0 = _base_price(symbol)
    vol = p0 * 0.0008
    noise = rng.normal(0, vol, count)
    closes = np.empty(count)
    p = p0
    drift = 0.0
    for i in range(count):
        if i % 180 == 0:                       # new regime ~ every 15h of 5M data
            drift = rng.normal(0, vol * 0.02)  # mild, realistic persistent bias
        p += drift + noise[i]
        closes[i] = p
    wicks = np.abs(rng.normal(0, vol, count))
    vols = np.abs(rng.normal(1000, 300, count)).astype(int)
    rows = []
    start = end - timedelta(minutes=5 * count)
    ac = _asset_class(symbol)
    for i in range(count):
        c = float(closes[i])
        o = float(closes[i - 1]) if i > 0 else c
        hi = max(o, c) + float(wicks[i])
        lo = min(o, c) - float(wicks[i])
        rows.append({
            "symbol": symbol, "asset_class": ac, "exchange": "SYNTH",
            "timestamp": (start + timedelta(minutes=5 * i)).isoformat(),
            "open": round(o, 6), "high": round(hi, 6), "low": round(lo, 6),
            "close": round(c, 6), "volume": float(vols[i]),
        })
    return rows


def _asset_class(symbol: str) -> str:
    s = symbol.upper()
    if "XAU" in s or "XAG" in s or "GOLD" in s or "SILVER" in s:
        return "metals"
    if "BTC" in s or "ETH" in s:
        return "crypto"
    if "/" in s:
        return "forex"
    return "stocks"


def _to_df(candles: List[Dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.set_index("timestamp").sort_index()


def resample(candles: List[Dict], target_tf: str) -> List[Dict]:
    """Resample base (5M) candles into a higher timeframe. Only closed bars returned."""
    if target_tf == "5M":
        return candles
    df = _to_df(candles)
    rule = PANDAS_RULE[target_tf]
    agg = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()
    symbol = candles[0]["symbol"] if candles else "UNKNOWN"
    out = []
    for ts, r in agg.iterrows():
        out.append({
            "symbol": symbol, "asset_class": _asset_class(symbol), "exchange": "SYNTH",
            "timestamp": ts.isoformat(), "open": round(float(r["open"]), 6),
            "high": round(float(r["high"]), 6), "low": round(float(r["low"]), 6),
            "close": round(float(r["close"]), 6), "volume": float(r["volume"]),
        })
    return out


def multi_timeframe(candles_5m: List[Dict]) -> Dict[str, List[Dict]]:
    return {
        "5M": candles_5m,
        "10M": resample(candles_5m, "10M"),
        "15M": resample(candles_5m, "15M"),
        "1H": resample(candles_5m, "1H"),
        "4H": resample(candles_5m, "4H"),
        "1D": resample(candles_5m, "1D"),
    }


def parse_csv(content: str, symbol: str = "UPLOAD") -> List[Dict]:
    """Parse uploaded OHLC CSV. Expects columns: timestamp/date, open, high, low, close, [volume]."""
    df = pd.read_csv(io.StringIO(content))
    df.columns = [c.strip().lower() for c in df.columns]
    tcol = next((c for c in ("timestamp", "date", "time", "datetime") if c in df.columns), None)
    if tcol is None:
        raise ValueError("CSV must contain a timestamp/date column")
    out = []
    for _, r in df.iterrows():
        out.append({
            "symbol": symbol, "asset_class": _asset_class(symbol), "exchange": "CSV",
            "timestamp": pd.to_datetime(r[tcol], utc=True).isoformat(),
            "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": float(r["volume"]) if "volume" in df.columns else 0.0,
        })
    return out



def get_candles(symbol: str, timeframe: str = "5M", limit: int = 300):
    """Return (candles, source, state). Uses live provider when a key is set, else synthetic.

    Falls back to synthetic on any provider error so the terminal never goes blank
    (the reason is surfaced in `source`).
    """
    from . import providers as P
    state = "HISTORICAL" if limit > 300 else "REAL-TIME"
    if P.has_key():
        try:
            rows = P.twelvedata_ohlc(symbol, timeframe, outputsize=limit)
            if timeframe == "10M":
                rows = resample(rows, "10M")
            return rows[-limit:], "twelvedata", state
        except P.ProviderError as e:
            base = generate_5m(symbol, count=max(limit * TF_MINUTES.get(timeframe, 5) // 5, 500))
            series = resample(base, timeframe) if timeframe != "5M" else base
            return series[-limit:], f"synthetic (fallback: {e.code})", state
    base = generate_5m(symbol, count=max(limit * TF_MINUTES.get(timeframe, 5) // 5, 500))
    series = resample(base, timeframe) if timeframe != "5M" else base
    return series[-limit:], "synthetic", state
