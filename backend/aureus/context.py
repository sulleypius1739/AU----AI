"""News + fundamental context. Deterministic reference data (not a live feed).

Clearly labelled as reference/BETA so nothing is faked as live. News risk gates are
advisory only — they never manufacture a trade, and never override V4 hard gates.
"""
from datetime import datetime, timezone, timedelta

_HIGH = {"CPI", "NFP", "FOMC", "Fed Decision", "ECB Rate Decision", "GDP"}
_MED = {"PPI", "Retail Sales", "Unemployment Rate", "PMI"}


def economic_calendar(symbol: str = "XAU/USD") -> dict:
    now = datetime.now(timezone.utc)
    events = [
        {"headline": "US CPI (YoY)", "event": "CPI", "time": (now + timedelta(hours=6)).isoformat(),
         "source": "BLS", "importance": "HIGH", "affected": "USD, XAU/USD",
         "interpretation": "Hotter CPI -> USD strength -> gold headwind"},
        {"headline": "FOMC Rate Decision", "event": "FOMC", "time": (now + timedelta(days=2)).isoformat(),
         "source": "Federal Reserve", "importance": "HIGH", "affected": "USD, indices, metals",
         "interpretation": "Hawkish hold pressures risk assets"},
        {"headline": "ECB Press Conference", "event": "ECB Rate Decision", "time": (now + timedelta(days=1)).isoformat(),
         "source": "ECB", "importance": "HIGH", "affected": "EUR crosses",
         "interpretation": "Dovish tone weakens EUR"},
        {"headline": "US Retail Sales", "event": "Retail Sales", "time": (now + timedelta(hours=30)).isoformat(),
         "source": "US Census", "importance": "MEDIUM", "affected": "USD",
         "interpretation": "Consumer strength supports USD"},
    ]
    return {"symbol": symbol, "source": "reference", "events": events,
            "note": "Reference calendar (BETA) — not a live feed."}


def news_risk(symbol: str = "XAU/USD") -> dict:
    cal = economic_calendar(symbol)
    now = datetime.now(timezone.utc)
    soonest_high = None
    for e in cal["events"]:
        if e["importance"] == "HIGH":
            dt = datetime.fromisoformat(e["time"])
            hrs = (dt - now).total_seconds() / 3600
            if 0 <= hrs and (soonest_high is None or hrs < soonest_high["hours"]):
                soonest_high = {"event": e["event"], "hours": round(hrs, 1)}
    if soonest_high and soonest_high["hours"] <= 8:
        risk = "HIGH"
    elif soonest_high and soonest_high["hours"] <= 36:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return {"symbol": symbol, "news_risk": risk, "next_high_impact": soonest_high,
            "note": "Advisory only — AUREUS never manufactures a trade around news."}


def fundamentals(symbol: str = "XAU/USD") -> dict:
    s = symbol.upper()
    if "XAU" in s or "GOLD" in s:
        data = {"usd_strength": "Firm", "real_yields": "Elevated", "fed_expectations": "Hawkish hold",
                "inflation": "Sticky", "risk_sentiment": "Cautious", "central_bank_demand": "Strong",
                "fundamental_bias": "NEUTRAL-BEARISH (yields cap upside; CB demand supports)"}
    elif "/" in s:
        base, quote = (s.split("/") + ["USD"])[:2]
        data = {"base_currency": base, "quote_currency": quote,
                "relative_macro_strength": f"{quote} > {base} (USD carry advantage)",
                "interest_rate_differential": "Favours USD", "central_bank_stance": "Divergent",
                "fundamental_bias": "Depends on rate differential"}
    else:
        data = {"economic_environment": "Late-cycle", "interest_rate_context": "Restrictive",
                "inflation": "Moderating", "employment": "Resilient", "gdp": "Slowing",
                "central_bank_expectations": "Hold", "risk_sentiment": "Mixed",
                "fundamental_bias": "NEUTRAL"}
    return {"symbol": symbol, "source": "reference", **data,
            "note": "Fundamental bias is CONTEXT only and never overrides V4 technical structure."}


def confluence(technical_bias: str, symbol: str = "XAU/USD") -> dict:
    fund = fundamentals(symbol)["fundamental_bias"]
    aligned = technical_bias.upper() in fund.upper()
    return {"technical_bias": technical_bias, "fundamental_bias": fund,
            "confluence": "ALIGNED" if aligned else "CONFLICT",
            "note": "V4 hard-gate technical structure remains authoritative."}
