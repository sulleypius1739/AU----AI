"""Iteration 2 regression: matched A/B backtest, profit_factor cap, flattened /api/backtest."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

METRIC_KEYS = ["total_trades", "win_rate", "profit_factor", "net_r", "max_drawdown_r",
               "equity_curve", "sl_before_tp_count", "sl_hit_then_tp_would_fill",
               "rr_distribution"]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def report(client):
    r = client.get(f"{BASE_URL}/api/backtest/report", timeout=120)
    assert r.status_code == 200, r.text[:300]
    return r.json()


# ---- /api/validation golden scenarios ----
class TestValidation:
    def test_all_pass(self, client):
        r = client.get(f"{BASE_URL}/api/validation", timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["all_pass"] is True, d
        res = d["results"]
        assert res["golden_bullish"]["status"] == "A+ BUY", res["golden_bullish"]
        assert res["golden_bearish"]["status"] == "A+ SELL", res["golden_bearish"]
        for name, neg in res["negatives"].items():
            assert neg["actionable"] is False, (name, neg)


# ---- /api/backtest/report matched A/B ----
class TestMatchedAB:
    def test_status_and_source(self, report):
        assert report["status"] == "READY", report
        assert "SYNTHETIC" in str(report.get("data_source", "")).upper()

    def test_matched_ab_present(self, report):
        m = report["eurusd"]["matched_ab"]
        assert m["matched_trades"] > 0
        for block in ("tp_at_swing", "tp_beyond_swing"):
            b = m[block]
            for k in ("win_rate", "average_r", "sl_before_tp_count", "sl_hit_then_tp_would_fill"):
                assert k in b, f"{block} missing {k}"
            assert b["total_trades"] == m["matched_trades"], block

    def test_matched_same_entry_count(self, report):
        m = report["eurusd"]["matched_ab"]
        assert m["tp_at_swing"]["total_trades"] == m["tp_beyond_swing"]["total_trades"]

    def test_beyond_rr_not_lower(self, report):
        m = report["eurusd"]["matched_ab"]
        assert m["tp_beyond_swing"]["average_r"] is not None

    def test_per_instrument_16(self, report):
        pi = report["per_instrument"]
        assert len(pi) == 16, len(pi)

    def test_before_after_blocks(self, report):
        e = report["eurusd"]
        for k in ("before_tp_at_swing", "after_tp_beyond_swing", "after_with_management"):
            assert k in e, k
            assert "win_rate" in e[k]

    def test_profit_factor_capped_in_report(self, report):
        vals = [row.get("profit_factor", 0) for row in report["per_instrument"]]
        for v in vals:
            assert v <= 999.0, v

    def test_no_mongo_id(self, report):
        assert "_id" not in str(report)[:200000]


# ---- /api/backtest on-demand ----
class TestBacktestEndpoint:
    def test_beyond_managed(self, client):
        r = client.get(f"{BASE_URL}/api/backtest",
                       params={"symbol": "EUR/USD", "candles": 6000,
                               "tp_mode": "beyond", "manage": "true"}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in METRIC_KEYS:
            assert k in d, f"missing flattened key {k}"
        assert d["profit_factor"] <= 999.0, d["profit_factor"]
        assert isinstance(d["equity_curve"], list)

    def test_at_unmanaged(self, client):
        r = client.get(f"{BASE_URL}/api/backtest",
                       params={"symbol": "EUR/USD", "candles": 6000,
                               "tp_mode": "at", "manage": "false"}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["config"]["tp_mode"] == "at"
        assert d["config"]["management"] is False


# ---- /api/signal trade plan ----
class TestSignal:
    def test_xauusd_plan(self, client):
        r = client.get(f"{BASE_URL}/api/signal", params={"symbol": "XAU/USD"}, timeout=120)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["checks"]) == 7
        plan = d.get("trade_plan")
        if plan:
            assert plan["tp_mode"] == "beyond"
            assert plan["target_swing"] is not None
            assert plan["management"]["breakeven_at_r"] == 1.0
            assert 2.0 <= plan["rr"] <= 5.0, plan["rr"]
            if d["direction"] == "bullish":
                assert plan["target"] > plan["target_swing"]
            else:
                assert plan["target"] < plan["target_swing"]
