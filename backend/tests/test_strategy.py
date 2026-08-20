"""AUREUS V4 strategy validation suite — golden + negative scenarios.

Run:  cd /app/backend && python -m pytest tests/ -v
This suite is MANDATORY before major releases (spec sections 8 & 47 Phase 1).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aureus import strategy as S
from aureus import scenarios as SC


def test_golden_bullish_produces_a_plus_buy():
    sig = S.build_signal(SC.golden_bullish(), symbol="EURUSD")
    assert sig["checks"]["htf_direction"]["passed"], sig["checks"]
    assert sig["checks"]["poi"]["passed"], sig["checks"]
    assert sig["checks"]["market_shift"]["passed"], sig["checks"]
    assert sig["checks"]["liquidity_sweep"]["passed"], sig["checks"]
    assert sig["checks"]["ltf_confirmation"]["passed"], sig["checks"]
    assert sig["checks"]["poi_mitigation"]["passed"], sig["checks"]
    assert sig["checks"]["rr"]["passed"], sig["checks"]
    assert sig["status"] == S.A_PLUS_BUY
    assert 2.0 <= sig["trade_plan"]["rr"] <= 5.0


def test_golden_bearish_produces_a_plus_sell():
    sig = S.build_signal(SC.golden_bearish(), symbol="EURUSD")
    assert sig["status"] == S.A_PLUS_SELL, sig["checks"]
    assert 2.0 <= sig["trade_plan"]["rr"] <= 5.0


def test_negative_scenarios_never_actionable():
    for name, tf in SC.negatives().items():
        sig = S.build_signal(tf, symbol=name)
        assert not sig["actionable"], f"{name} must NOT produce a signal (got {sig['status']})"
        assert sig["status"] in (S.WAIT, S.WATCH, S.ARMED, S.CONFIRMED, S.INVALIDATED)


def test_rr_band_enforced():
    from aureus.engine import compute_risk
    assert compute_risk(10000, 1, 1.1460, 1.1210, 1.2085)["rr_valid"]      # ~2.5R
    assert not compute_risk(10000, 1, 1.1460, 1.1210, 1.1500)["rr_valid"]  # < 2R
    assert not compute_risk(10000, 1, 1.1460, 1.1210, 1.5000)["rr_valid"]  # > 5R
