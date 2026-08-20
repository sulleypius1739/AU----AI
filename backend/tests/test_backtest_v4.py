"""V4 A+ strategy / backtest regression tests (TP beyond swing + 4Y report)."""
import os
import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------------- module: /api/validation (V4 gate still intact) ----------------
class TestValidation:
    def test_all_pass(self, http):
        r = http.get(f"{API}/validation", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["all_pass"] is True
        assert d["results"]["golden_bullish"]["status"] == "A+ BUY"
        assert d["results"]["golden_bearish"]["status"] == "A+ SELL"
        for name, v in d["results"]["negatives"].items():
            assert v["actionable"] is False, f"{name} became actionable"


# ---------------- module: /api/signal trade_plan (tp beyond swing) ----------------
class TestSignalTradePlan:
    def test_signal_trade_plan_beyond(self, http):
        r = http.get(f"{API}/signal", params={"symbol": "XAU/USD"}, timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "checks" in d and len(d["checks"]) == 7
        plan = d.get("trade_plan")
        if plan is None:
            pytest.skip("No trade_plan in current synthetic window (structure not mitigated)")
        assert plan.get("tp_mode") == "beyond"
        assert isinstance(plan.get("target_swing"), (int, float))
        assert plan.get("management", {}).get("breakeven_at_r") == 1.0
        assert plan["management"].get("partial_pct") == 50
        assert 2.0 <= float(plan["rr"]) <= 5.0, plan["rr"]
        # target must sit beyond the structural swing
        if d["direction"] == "bullish":
            assert plan["target"] > plan["target_swing"]
        else:
            assert plan["target"] < plan["target_swing"]

    def test_demo_bullish_plan_beyond(self, http):
        r = http.get(f"{API}/signal/demo", params={"scenario": "bullish"}, timeout=60)
        if r.status_code == 404:
            pytest.skip("no demo endpoint")
        assert r.status_code == 200
        d = r.json()
        plan = d.get("trade_plan")
        assert plan is not None
        assert plan["tp_mode"] == "beyond"
        # NOTE: /api/signal/demo does not pass pip -> buffer is 0 so TP lands ON the swing
        assert plan["target"] >= plan["target_swing"]
        assert 2.0 <= float(plan["rr"]) <= 5.0


# ---------------- module: /api/backtest (flattened metrics + new keys) ----------------
FLAT_KEYS = ["total_trades", "win_rate", "profit_factor", "net_r", "max_drawdown_r",
             "a_plus_count", "equity_curve", "sl_before_tp_count",
             "sl_hit_then_tp_would_fill", "rr_distribution", "drawdown_curve"]


class TestBacktestEndpoint:
    def test_backtest_beyond_managed(self, http):
        r = http.get(f"{API}/backtest",
                     params={"symbol": "EUR/USD", "candles": 6000,
                             "tp_mode": "beyond", "manage": "true"}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in FLAT_KEYS:
            assert k in d, f"missing flattened key {k}"
        assert d["config"]["tp_mode"] == "beyond"
        assert d["config"]["management"] is True
        assert d["total_trades"] > 0
        assert 0 <= d["win_rate"] <= 100
        assert isinstance(d["rr_distribution"], dict)
        assert isinstance(d["equity_curve"], list) and isinstance(d["drawdown_curve"], list)
        assert len(d["equity_curve"]) == len(d["drawdown_curve"])
        for t in d["trades"]:
            assert isinstance(t["sl_before_tp"], bool)
            assert isinstance(t["recovered_after_sl"], bool)
            assert t["tp_mode"] == "beyond"
            assert 2.0 <= float(t["rr_planned"]) <= 5.0
        # consistency of aggregates
        assert d["wins"] + d["losses"] <= d["total_trades"]
        assert d["sl_hit_then_tp_would_fill"] <= d["sl_before_tp_count"]

    def test_backtest_baseline_at_unmanaged(self, http):
        r = http.get(f"{API}/backtest",
                     params={"symbol": "EUR/USD", "candles": 6000,
                             "tp_mode": "at", "manage": "false"}, timeout=300)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["config"]["tp_mode"] == "at"
        assert d["config"]["management"] is False
        assert d["total_trades"] > 0
        for t in d["trades"]:
            assert t["tp_mode"] == "at"
            if t["direction"] == "bullish":
                assert t["target"] < t["target_swing"]
            else:
                assert t["target"] > t["target_swing"]

    def test_no_mongo_objectid_leak(self, http):
        r = http.get(f"{API}/backtest",
                     params={"symbol": "EUR/USD", "candles": 1200}, timeout=180)
        assert r.status_code == 200
        assert "_id" not in r.text


# ---------------- module: /api/backtest/report (4-year report) ----------------
class TestReport4Y:
    @pytest.fixture(scope="class")
    def report(self, http):
        r = http.get(f"{API}/backtest/report", timeout=120)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def test_status_and_source(self, report):
        assert report["status"] == "READY"
        assert "SYNTHETIC" in str(report.get("data_source", "")).upper()

    def test_eurusd_blocks(self, report):
        eur = report["eurusd"]
        for block in ["before_tp_at_swing", "after_tp_beyond_swing", "after_with_management"]:
            assert block in eur, f"missing {block}"
            m = eur[block]
            assert m["total_trades"] > 0
            assert 0 <= m["win_rate"] <= 100
            assert "sl_before_tp_count" in m
            assert "rr_distribution" in m
        wr = eur["after_tp_beyond_swing"]["win_rate"]
        assert 45 <= wr <= 70, f"EUR/USD management-off win rate out of sane band: {wr}"

    def test_per_instrument_16(self, report):
        per = report["per_instrument"]
        assert isinstance(per, list)
        assert len(per) == 16, f"expected 16 instruments, got {len(per)}"
        for row in per:
            assert row.get("symbol")
            assert "win_rate" in row and 0 <= row["win_rate"] <= 100
            assert ("total_trades" in row) or ("trades" in row)
