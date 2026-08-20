"""End-to-end API tests for AUREUS AI backend.

Uses the public REACT_APP_BACKEND_URL (with /api prefix). Cold start of the
backend may take ~6s; a per-test warmup request is done in a session-scoped
fixture.
"""
import os
import time
import uuid
import pytest
import requests
from pathlib import Path

# Load REACT_APP_BACKEND_URL from /app/frontend/.env if it's not exported
if "REACT_APP_BACKEND_URL" not in os.environ:
    env_path = Path("/app/frontend/.env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip().strip('"')
                break

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ALLOWED_STATUSES = {"WAIT", "WATCH", "ARMED", "CONFIRMED", "A+ BUY", "A+ SELL",
                    "INVALIDATED", "EXPIRED"}


def _retry_get(session, url, timeout=60, retries=2):
    """GET with retry on transient 502/503/504 from ingress."""
    last = None
    for _ in range(retries + 1):
        r = session.get(url, timeout=timeout)
        last = r
        if r.status_code not in (502, 503, 504):
            return r
        time.sleep(2)
    return last


def _retry_post(session, url, json_body=None, timeout=60, retries=2):
    last = None
    for _ in range(retries + 1):
        r = session.post(url, json=json_body, timeout=timeout)
        last = r
        if r.status_code not in (502, 503, 504):
            return r
        time.sleep(2)
    return last


# --------------------------- fixtures ---------------------------
@pytest.fixture(scope="session")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Warm cold start
    for _ in range(3):
        try:
            r = s.get(f"{API}/", timeout=15)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(1)
    return s


@pytest.fixture(scope="session")
def president_session(http):
    """Logged-in session cookie for the seeded president admin."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "president@aureus.ai", "password": "Aureus2020!"},
               timeout=20)
    assert r.status_code == 200, f"president login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def trader_session(http):
    """Session for a freshly-registered trader."""
    s = requests.Session()
    email = f"trader_{uuid.uuid4().hex[:10]}@example.com"
    r = s.post(f"{API}/auth/register",
               json={"email": email, "password": "Trader1234!", "name": "Test Trader"},
               timeout=20)
    assert r.status_code == 200, f"register failed: {r.status_code} {r.text}"
    return s, email


# --------------------------- root / admin ---------------------------
class TestRoot:
    def test_root(self, http):
        r = http.get(f"{API}/", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("platform") == "AUREUS AI"

    def test_admin_status(self, http):
        r = http.get(f"{API}/admin/status", timeout=20)
        assert r.status_code == 200
        j = r.json()
        for key in ("aureus_engine", "data_feed", "signal_engine", "risk_engine",
                    "news_engine", "backtest_engine", "ai_engine", "database"):
            assert key in j, f"missing {key} in admin status"
        assert j["validation_all_pass"] is True
        assert j["database"] == "ONLINE"


# --------------------------- validation ---------------------------
class TestValidation:
    def test_validation_all_pass(self, http):
        r = http.get(f"{API}/validation", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["all_pass"] is True, f"validation failed: {j}"
        assert j["results"]["golden_bullish"]["status"] == "A+ BUY"
        assert j["results"]["golden_bearish"]["status"] == "A+ SELL"

        expected_neg = {"NO_POI", "NO_15M_MARKET_SHIFT", "NO_FINAL_LIQUIDITY_SEQUENCE",
                        "NO_10M_MARKET_SHIFT", "10M_WRONG_DIRECTION", "POI_NOT_MITIGATED"}
        negs = j["results"]["negatives"]
        assert expected_neg.issubset(set(negs.keys())), f"missing negatives: {set(negs.keys())}"
        for name in expected_neg:
            assert negs[name]["actionable"] is False, f"{name} must not be actionable"
            assert negs[name]["pass"] is True


# --------------------------- signal demo ---------------------------
class TestSignalDemo:
    def test_bullish_demo_a_plus_buy(self, http):
        r = http.get(f"{API}/signal/demo?direction=bullish", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "A+ BUY", j
        rr = j["trade_plan"]["rr"]
        assert 2.0 <= rr <= 5.0, f"rr={rr}"

    def test_bearish_demo_a_plus_sell(self, http):
        r = http.get(f"{API}/signal/demo?direction=bearish", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "A+ SELL", j
        rr = j["trade_plan"]["rr"]
        assert 2.0 <= rr <= 5.0


# --------------------------- live signal ---------------------------
class TestSignal:
    def test_signal_xauusd_structure(self, http):
        r = http.get(f"{API}/signal?symbol=XAU/USD", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert set(j["checks"].keys()) == {
            "htf_direction", "poi", "market_shift", "liquidity_sweep",
            "ltf_confirmation", "poi_mitigation", "rr",
        }
        assert j["status"] in ALLOWED_STATUSES, j["status"]
        assert isinstance(j.get("philosophy"), str) and len(j["philosophy"]) > 0


# --------------------------- candles ---------------------------
class TestCandles:
    def test_candles_eurusd_4h(self, http):
        r = _retry_get(http, f"{API}/candles?symbol=EUR/USD&timeframe=4H&limit=100", timeout=60)
        assert r.status_code == 200, f"{r.status_code}"
        j = r.json()
        assert j["symbol"] == "EUR/USD"
        assert j["timeframe"] == "4H"
        assert "state" in j
        assert isinstance(j["candles"], list) and len(j["candles"]) > 0
        c = j["candles"][0]
        for k in ("open", "high", "low", "close", "volume", "timestamp"):
            assert k in c, f"missing candle field {k}"


# --------------------------- instruments ---------------------------
class TestInstruments:
    def test_instruments_search_gold(self, http):
        r = http.get(f"{API}/instruments?q=gold", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["results"]) >= 1
        for i in j["results"]:
            for k in ("symbol", "name", "exchange", "country", "asset_class"):
                assert k in i
        # Gold spot should be there
        symbols = [i["symbol"] for i in j["results"]]
        assert any("XAU" in s for s in symbols), symbols

    def test_instruments_empty_q_returns_all(self, http):
        r = http.get(f"{API}/instruments", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert len(j["results"]) >= 10  # at least the seeded list


# --------------------------- risk ---------------------------
class TestRisk:
    def test_risk_valid_25r(self, http):
        r = http.post(f"{API}/risk", json={
            "equity": 10000, "risk_pct": 1, "entry": 1.1460,
            "stop": 1.1210, "target": 1.2085,
        }, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["rr_valid"] is True
        assert 2.4 <= j["rr"] <= 2.6, f"rr={j['rr']}"

    def test_risk_below_2r_invalid(self, http):
        r = http.post(f"{API}/risk", json={
            "equity": 10000, "risk_pct": 1, "entry": 1.1460,
            "stop": 1.1210, "target": 1.1500,
        }, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["rr_valid"] is False
        assert j["rr"] < 2.0

    def test_risk_above_5r_invalid(self, http):
        r = http.post(f"{API}/risk", json={
            "equity": 10000, "risk_pct": 1, "entry": 1.1460,
            "stop": 1.1210, "target": 1.5000,
        }, timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["rr_valid"] is False
        assert j["rr"] > 5.0


# --------------------------- backtest ---------------------------
class TestBacktest:
    def test_backtest_eurusd(self, http):
        r = _retry_get(http, f"{API}/backtest?symbol=EUR/USD&candles=6000", timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        j = r.json()
        for k in ("trades", "total_trades", "win_rate", "profit_factor",
                 "net_r", "max_drawdown_r", "a_plus_count", "equity_curve"):
            assert k in j, f"backtest missing {k}"
        assert isinstance(j["trades"], list)
        assert isinstance(j["equity_curve"], list)


# --------------------------- auth ---------------------------
class TestAuth:
    def test_president_login_and_me(self, http):
        s = requests.Session()
        r = s.post(f"{API}/auth/login",
                   json={"email": "president@aureus.ai", "password": "Aureus2020!"},
                   timeout=20)
        assert r.status_code == 200, r.text
        user = r.json()
        assert user["role"] == "president"
        assert user["email"] == "president@aureus.ai"
        # cookies present
        assert "access_token" in s.cookies or any("access_token" == c.name for c in s.cookies)
        # /me returns same user
        r2 = s.get(f"{API}/auth/me", timeout=15)
        assert r2.status_code == 200
        me = r2.json()
        assert me.get("email") == "president@aureus.ai"
        assert me.get("role") == "president"

    def test_login_wrong_password(self, http):
        r = http.post(f"{API}/auth/login",
                      json={"email": "president@aureus.ai", "password": "WRONG_PW"},
                      timeout=15)
        assert r.status_code == 401

    def test_register_creates_trader(self, http):
        s = requests.Session()
        email = f"trader_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/auth/register",
                   json={"email": email, "password": "Trader1234!", "name": "Reg Test"},
                   timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["role"] == "trader"
        assert j["email"] == email
        # verify /me
        r2 = s.get(f"{API}/auth/me", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["email"] == email

    def test_me_unauthenticated(self, http):
        r = requests.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 401


# --------------------------- journal ---------------------------
class TestJournal:
    def test_journal_crud(self, trader_session):
        s, email = trader_session
        # CREATE
        payload = {
            "symbol": "EUR/USD", "direction": "bullish",
            "entry": 1.1460, "stop": 1.1210, "target": 1.2085,
            "risk_pct": 1.0, "result": "open",
            "user_notes": "TEST_ entry via automated suite",
        }
        r = s.post(f"{API}/journal", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["symbol"] == "EUR/USD"
        assert j["direction"] == "bullish"
        assert j.get("rr") is not None
        assert 2.4 <= j["rr"] <= 2.6, f"rr={j['rr']}"
        assert j.get("position_size") is not None
        entry_id = j.get("id") or j.get("_id")
        assert entry_id, f"no id returned: {j}"

        # LIST
        r2 = s.get(f"{API}/journal", timeout=15)
        assert r2.status_code == 200
        items = r2.json()
        assert any((it.get("id") or it.get("_id")) == entry_id for it in items)

        # FILTER by symbol
        r3 = s.get(f"{API}/journal?symbol=EUR/USD", timeout=15)
        assert r3.status_code == 200
        assert all(it["symbol"] == "EUR/USD" for it in r3.json())

        # FILTER by direction
        r4 = s.get(f"{API}/journal?direction=bullish", timeout=15)
        assert r4.status_code == 200
        assert all(it["direction"] == "bullish" for it in r4.json())

        # DELETE
        r5 = s.delete(f"{API}/journal/{entry_id}", timeout=15)
        assert r5.status_code == 200
        # verify removed
        r6 = s.get(f"{API}/journal", timeout=15)
        assert all((it.get("id") or it.get("_id")) != entry_id for it in r6.json())

    def test_journal_requires_auth(self, http):
        r = requests.get(f"{API}/journal", timeout=15)
        assert r.status_code == 401


# --------------------------- context (news/fundamentals) ---------------------------
class TestContext:
    def test_news(self, http):
        r = http.get(f"{API}/news?symbol=XAU/USD", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j.get("source") == "reference"
        assert isinstance(j["events"], list) and len(j["events"]) > 0
        for e in j["events"]:
            for k in ("headline", "event", "time", "importance"):
                assert k in e

    def test_news_risk(self, http):
        r = http.get(f"{API}/news/risk?symbol=XAU/USD", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["news_risk"] in ("LOW", "MEDIUM", "HIGH")

    def test_fundamentals(self, http):
        r = http.get(f"{API}/fundamentals?symbol=XAU/USD", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert "fundamental_bias" in j
        assert j.get("source") == "reference"

    def test_confluence(self, http):
        r = http.get(f"{API}/confluence?symbol=XAU/USD&technical_bias=BULLISH", timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert j["confluence"] in ("ALIGNED", "CONFLICT")


# --------------------------- AI explain ---------------------------
class TestAI:
    def test_ai_explain_bullish_connected(self, http):
        r = _retry_post(http, f"{API}/ai/explain",
                        json_body={"symbol": "XAU/USD", "direction": "bullish"},
                        timeout=90)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        j = r.json()
        # must include an underlying real engine signal
        assert "signal" in j
        assert j["signal"]["status"] == "A+ BUY", j["signal"]["status"]
        # must connect to real LLM (EMERGENT_LLM_KEY is set)
        assert j.get("ai_connected") is True, f"ai_connected false: {j}"
        assert j.get("status") == "CONNECTED"
        expl = j.get("explanation", "")
        assert isinstance(expl, str) and len(expl) > 50, f"short explanation: {expl!r}"
        # explanation should reference real engine terms, not hallucinate
        low = expl.lower()
        assert any(kw in low for kw in [
            "poi", "market shift", "sweep", "confirmation", "mitigation",
            "4h", "15m", "10m", "5m", "rr", "a+", "buy", "bullish",
        ]), f"explanation looks generic: {expl!r}"
