"""Iteration 3: live-provider layer (Twelve Data) with synthetic fallback.

Covers:
  * aureus.providers  -> has_key / ProviderError codes
  * aureus.data.get_candles -> (candles, source, state) fallback contract
  * GET /api/candles (all timeframes, source field)
  * GET /api/instruments (source field, empty q, filtered q)
  * GET /api/signal (synthetic fallback, 7 V4 checks)
  * GET /api/admin/status data_feed
"""
import os
import sys
import pytest
import requests
from dotenv import dotenv_values

sys.path.insert(0, "/app/backend")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
TIMEOUT = 60


@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- providers module (unit) ----------------
class TestProvidersUnit:
    def test_has_key_false_without_env(self):
        from aureus import providers as P
        assert P.has_key() is False, "TWELVE_DATA_API_KEY unexpectedly configured"

    def test_ohlc_raises_api_key_missing(self):
        from aureus import providers as P
        with pytest.raises(P.ProviderError) as ei:
            P.twelvedata_ohlc("EUR/USD", "5M", outputsize=10)
        assert ei.value.code == "API_KEY_MISSING"

    def test_search_raises_api_key_missing(self):
        from aureus import providers as P
        with pytest.raises(P.ProviderError) as ei:
            P.search("gold")
        assert ei.value.code == "API_KEY_MISSING"

    def test_interval_map_covers_ui_timeframes(self):
        from aureus import providers as P
        for tf in ["5M", "10M", "15M", "1H", "4H", "1D"]:
            assert tf in P.TD_INTERVAL


# ---------------- data.get_candles (unit) ----------------
class TestGetCandlesUnit:
    @pytest.mark.parametrize("tf", ["5M", "10M", "15M", "1H", "4H", "1D"])
    def test_returns_synthetic_triplet(self, tf):
        from aureus import data as D
        candles, source, state = D.get_candles("EUR/USD", tf, 50)
        assert source == "synthetic"
        assert state in ("REAL-TIME", "HISTORICAL")
        assert 0 < len(candles) <= 50
        row = candles[-1]
        for k in ("symbol", "asset_class", "exchange", "timestamp",
                  "open", "high", "low", "close", "volume"):
            assert k in row
        assert row["low"] <= row["open"] <= row["high"]
        assert row["low"] <= row["close"] <= row["high"]

    def test_deterministic(self):
        from aureus import data as D
        a, _, _ = D.get_candles("XAU/USD", "15M", 30)
        b, _, _ = D.get_candles("XAU/USD", "15M", 30)
        assert [c["close"] for c in a] == [c["close"] for c in b]

    def test_state_historical_for_large_limit(self):
        from aureus import data as D
        _, _, state = D.get_candles("EUR/USD", "5M", 400)
        assert state == "HISTORICAL"

    def test_provider_error_falls_back_to_synthetic(self, monkeypatch):
        """With a key set but the provider failing, source must be a synthetic fallback."""
        from aureus import data as D
        from aureus import providers as P
        monkeypatch.setenv("TWELVE_DATA_API_KEY", "dummy-key")

        def boom(*a, **k):
            raise P.ProviderError("API_RATE_LIMIT", "boom")
        monkeypatch.setattr(P, "twelvedata_ohlc", boom)
        candles, source, _ = D.get_candles("EUR/USD", "5M", 40)
        assert source == "synthetic (fallback: API_RATE_LIMIT)"
        assert len(candles) == 40


# ---------------- GET /api/candles ----------------
class TestCandlesEndpoint:
    @pytest.mark.parametrize("tf", ["5M", "10M", "15M", "1H", "4H", "1D"])
    def test_candles_per_timeframe(self, api, tf):
        r = api.get(f"{BASE_URL}/api/candles",
                    params={"symbol": "EUR/USD", "timeframe": tf, "limit": 50},
                    timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["symbol"] == "EUR/USD"
        assert d["timeframe"] == tf
        assert d["source"] == "synthetic", d["source"]
        assert d["state"] == "REAL-TIME"
        assert len(d["candles"]) > 0
        assert len(d["candles"]) <= 50
        assert "_id" not in r.text

    def test_candles_unknown_symbol_still_200(self, api):
        r = api.get(f"{BASE_URL}/api/candles",
                    params={"symbol": "ZZZ/ZZZ", "timeframe": "5M", "limit": 10},
                    timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["source"] == "synthetic"
        assert len(r.json()["candles"]) == 10

    def test_candles_timestamps_ascending(self, api):
        r = api.get(f"{BASE_URL}/api/candles",
                    params={"symbol": "XAU/USD", "timeframe": "15M", "limit": 40},
                    timeout=TIMEOUT)
        ts = [c["timestamp"] for c in r.json()["candles"]]
        assert ts == sorted(ts)


# ---------------- GET /api/instruments ----------------
class TestInstrumentsEndpoint:
    def test_search_gold_builtin_source(self, api):
        r = api.get(f"{BASE_URL}/api/instruments", params={"q": "gold"}, timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "builtin"
        assert len(d["results"]) >= 1
        assert any("XAU" in x["symbol"] for x in d["results"])

    def test_empty_query_returns_full_list(self, api):
        r = api.get(f"{BASE_URL}/api/instruments", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "builtin"
        assert len(d["results"]) >= 16
        for row in d["results"]:
            assert {"symbol", "name", "exchange", "country", "asset_class"} <= set(row)

    def test_no_match_returns_empty(self, api):
        r = api.get(f"{BASE_URL}/api/instruments", params={"q": "zzzzz"}, timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["results"] == []


# ---------------- GET /api/signal ----------------
class TestSignalEndpoint:
    def test_signal_seven_checks(self, api):
        r = api.get(f"{BASE_URL}/api/signal", params={"symbol": "EUR/USD"}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["checks"]) == 7, [c.get("name") for c in d["checks"]]
        assert "status" in d and "actionable" in d
        assert isinstance(d["actionable"], bool)


# ---------------- GET /api/admin/status ----------------
class TestAdminStatus:
    def test_data_feed_synthetic(self, api):
        r = api.get(f"{BASE_URL}/api/admin/status", timeout=TIMEOUT)
        assert r.status_code == 200
        d = r.json()
        assert d["data_feed"] == "ONLINE (SYNTHETIC)", d["data_feed"]
        assert d["validation_all_pass"] is True
        assert d["database"] == "ONLINE"

    def test_validation_all_pass(self, api):
        r = api.get(f"{BASE_URL}/api/validation", timeout=TIMEOUT)
        assert r.status_code == 200
        assert r.json()["all_pass"] is True
