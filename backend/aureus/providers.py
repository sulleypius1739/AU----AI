"""Live market-data providers (Twelve Data primary, Polygon-ready).

The upstream API key is read from the backend environment and NEVER exposed to the
frontend. If no key is configured, callers fall back to the synthetic generator.
Normalizes every response to the common OHLC schema.
"""
import os
import requests

TD_URL = "https://api.twelvedata.com"
TD_INTERVAL = {"5M": "5min", "10M": "5min", "15M": "15min",
               "1H": "1h", "4H": "4h", "1D": "1day"}


class ProviderError(Exception):
    def __init__(self, code: str, message: str = ""):
        self.code = code
        super().__init__(message or code)


def has_key() -> bool:
    return bool(os.environ.get("TWELVE_DATA_API_KEY"))


def _asset_class(symbol: str) -> str:
    s = symbol.upper()
    if "XAU" in s or "XAG" in s or "GOLD" in s or "SILVER" in s:
        return "metals"
    if "BTC" in s or "ETH" in s:
        return "crypto"
    if "/" in s:
        return "forex"
    return "stocks"


def twelvedata_ohlc(symbol: str, timeframe: str, outputsize: int = 300):
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise ProviderError("API_KEY_MISSING", "TWELVE_DATA_API_KEY not configured")
    interval = TD_INTERVAL.get(timeframe, "5min")
    size = min(outputsize * 2, 5000) if timeframe == "10M" else min(outputsize, 5000)
    try:
        r = requests.get(f"{TD_URL}/time_series",
                         params={"symbol": symbol, "interval": interval, "outputsize": size},
                         headers={"Authorization": f"apikey {key}"}, timeout=12)
    except requests.RequestException as e:
        raise ProviderError("NETWORK_ERROR", str(e))
    if r.status_code == 429:
        raise ProviderError("API_RATE_LIMIT", "Twelve Data rate limit reached")
    try:
        payload = r.json()
    except ValueError:
        raise ProviderError("PROVIDER_ERROR", "Non-JSON response")
    if payload.get("status") == "error" or r.status_code >= 400:
        msg = payload.get("message", "provider error")
        code = "SYMBOL_NOT_SUPPORTED" if "not" in msg.lower() and "found" in msg.lower() else "PROVIDER_ERROR"
        raise ProviderError(code, msg)
    values = payload.get("values") or []
    if not values:
        raise ProviderError("HISTORICAL_DATA_UNAVAILABLE", "No values returned")
    ac = _asset_class(symbol)
    out = []
    for v in reversed(values):                       # provider returns newest-first
        def num(x):
            return float(x) if x not in (None, "") else 0.0
        out.append({
            "symbol": symbol, "asset_class": ac, "exchange": "TWELVEDATA",
            "timestamp": v["datetime"].replace(" ", "T"),
            "open": num(v.get("open")), "high": num(v.get("high")),
            "low": num(v.get("low")), "close": num(v.get("close")),
            "volume": num(v.get("volume")),
        })
    return out


def search(query: str):
    key = os.environ.get("TWELVE_DATA_API_KEY")
    if not key:
        raise ProviderError("API_KEY_MISSING")
    try:
        r = requests.get(f"{TD_URL}/symbol_search",
                         params={"symbol": query}, headers={"Authorization": f"apikey {key}"}, timeout=10)
        data = r.json().get("data", [])
    except Exception as e:
        raise ProviderError("PROVIDER_ERROR", str(e))
    return [{"symbol": d.get("symbol"), "name": d.get("instrument_name", ""),
             "exchange": d.get("exchange", ""), "country": d.get("country", ""),
             "asset_class": d.get("instrument_type", "")} for d in data[:12]]
