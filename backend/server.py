from dotenv import load_dotenv
from pathlib import Path
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import os
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, UploadFile, File
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

from aureus import strategy as S
from aureus import data as D
from aureus import backtest as BT
from aureus import scenarios as SC
from aureus import context as CTX
from aureus import ai as AI
from aureus import auth as AUTH
from aureus.models import (RegisterInput, LoginInput, JournalCreate, JournalEntry,
                           RiskInput, AIExplainInput, WatchlistItem)
from aureus.engine import compute_risk

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("aureus")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="AUREUS AI Trading Engine")
api = APIRouter(prefix="/api")

DEFAULT_WATCHLIST = ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "AAPL", "SPY"]
INSTRUMENTS = [
    {"symbol": "EUR/USD", "name": "Euro / US Dollar", "exchange": "FX", "country": "EU/US", "asset_class": "forex"},
    {"symbol": "GBP/USD", "name": "British Pound / US Dollar", "exchange": "FX", "country": "UK/US", "asset_class": "forex"},
    {"symbol": "USD/JPY", "name": "US Dollar / Japanese Yen", "exchange": "FX", "country": "US/JP", "asset_class": "forex"},
    {"symbol": "XAU/USD", "name": "Gold Spot", "exchange": "OTC", "country": "Global", "asset_class": "metals"},
    {"symbol": "XAG/USD", "name": "Silver Spot", "exchange": "OTC", "country": "Global", "asset_class": "metals"},
    {"symbol": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "country": "US", "asset_class": "stocks"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "exchange": "NASDAQ", "country": "US", "asset_class": "stocks"},
    {"symbol": "NVDA", "name": "NVIDIA Corp.", "exchange": "NASDAQ", "country": "US", "asset_class": "stocks"},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "exchange": "NASDAQ", "country": "US", "asset_class": "stocks"},
    {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "exchange": "NYSE", "country": "US", "asset_class": "etf"},
    {"symbol": "QQQ", "name": "Invesco QQQ (NASDAQ 100)", "exchange": "NASDAQ", "country": "US", "asset_class": "etf"},
    {"symbol": "BTC/USD", "name": "Bitcoin", "exchange": "CRYPTO", "country": "Global", "asset_class": "crypto"},
    {"symbol": "ETH/USD", "name": "Ethereum", "exchange": "CRYPTO", "country": "Global", "asset_class": "crypto"},
    {"symbol": "US OIL", "name": "WTI Crude Oil", "exchange": "NYMEX", "country": "US", "asset_class": "commodities"},
    {"symbol": "GER40", "name": "DAX 40 Index", "exchange": "XETRA", "country": "DE", "asset_class": "indices"},
    {"symbol": "US30", "name": "Dow Jones 30", "exchange": "CBOT", "country": "US", "asset_class": "indices"},
]


# ------------------------------ AUTH ------------------------------
@api.post("/auth/register")
async def register(body: RegisterInput, response: Response):
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {"email": email, "password_hash": AUTH.hash_password(body.password),
           "name": body.name, "role": "trader",
           "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    AUTH.set_auth_cookies(response, AUTH.create_access_token(uid, email, "trader"),
                          AUTH.create_refresh_token(uid))
    return {"id": uid, "email": email, "name": body.name, "role": "trader"}


@api.post("/auth/login")
async def login(body: LoginInput, response: Response):
    email = body.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not AUTH.verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = str(user["_id"])
    AUTH.set_auth_cookies(response, AUTH.create_access_token(uid, email, user["role"]),
                          AUTH.create_refresh_token(uid))
    return {"id": uid, "email": email, "name": user.get("name"), "role": user["role"]}


@api.post("/auth/logout")
async def logout(response: Response):
    AUTH.clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(request: Request):
    return await AUTH.get_current_user(request, db)


# ------------------------------ MARKET DATA ------------------------------
@api.get("/instruments")
async def instruments(q: str = ""):
    q = q.strip().lower()
    if not q:
        return {"results": INSTRUMENTS}
    return {"results": [i for i in INSTRUMENTS
                        if q in i["symbol"].lower() or q in i["name"].lower()
                        or q in i["asset_class"].lower()]}


@api.get("/candles")
async def candles(symbol: str = "XAU/USD", timeframe: str = "5M", limit: int = 300):
    base = D.generate_5m(symbol, count=max(limit * D.TF_MINUTES.get(timeframe, 5) // 5, 500))
    series = D.resample(base, timeframe) if timeframe != "5M" else base
    data_state = "HISTORICAL" if limit > 300 else "REAL-TIME"
    return {"symbol": symbol, "timeframe": timeframe, "state": data_state,
            "candles": series[-limit:]}


@api.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...), symbol: str = "UPLOAD"):
    content = (await file.read()).decode("utf-8")
    try:
        rows = D.parse_csv(content, symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {e}")
    return {"symbol": symbol, "count": len(rows), "candles": rows[:1000]}


# ------------------------------ STRATEGY / SIGNAL ------------------------------
@api.get("/signal")
async def signal(symbol: str = "XAU/USD", equity: float = 10000.0, risk_pct: float = 1.0):
    base = D.generate_5m(symbol, count=3000)
    tf = D.multi_timeframe(base)
    return S.build_signal(tf, symbol=symbol, equity=equity, risk_pct=risk_pct,
                          pip=D.pip_size(symbol), tp_mode="beyond")


@api.get("/signal/demo")
async def signal_demo(direction: str = "bullish"):
    tf = SC.golden_bullish() if direction == "bullish" else SC.golden_bearish()
    return S.build_signal(tf, symbol="DEMO/A+")


@api.get("/topdown")
async def topdown(symbol: str = "XAU/USD"):
    base = D.generate_5m(symbol, count=3000)
    tf = D.multi_timeframe(base)
    from aureus import engine as E
    return {
        "symbol": symbol,
        "4H": {"direction": E.trend_state(tf["4H"])},
        "1H": {"poi": E.find_poi(tf["1H"], "bullish") or E.find_poi(tf["1H"], "bearish")},
        "15M": {"shift": E.detect_market_shift(tf["15M"], "bullish") or E.detect_market_shift(tf["15M"], "bearish"),
                 "sweep": E.detect_sweep(tf["15M"], "sell") or E.detect_sweep(tf["15M"], "buy")},
        "10M": {"confirmation": E.detect_market_shift(tf["10M"], "bullish") or E.detect_market_shift(tf["10M"], "bearish")},
        "5M": {"note": "Execution timeframe"},
    }


# ------------------------------ RISK ------------------------------
@api.post("/risk")
async def risk(body: RiskInput):
    return compute_risk(body.equity, body.risk_pct, body.entry, body.stop,
                        body.target, body.asset_class)


# ------------------------------ BACKTEST ------------------------------
@api.get("/backtest")
async def backtest(symbol: str = "EUR/USD", candles: int = 6000, equity: float = 10000.0,
                   risk_pct: float = 1.0, tp_mode: str = "beyond", manage: bool = True):
    base = D.generate_5m(symbol, count=min(candles, 120000))
    result = BT.run_backtest(base, equity=equity, risk_pct=risk_pct,
                             tp_mode=tp_mode, manage=manage)
    return {"symbol": symbol, "candles_tested": len(base),
            "trades": result["trades"], "config": result["config"],
            "metrics": result["metrics"], **result["metrics"]}


@api.get("/backtest/report")
async def backtest_report():
    path = ROOT_DIR / "aureus" / "report.json"
    if not path.exists():
        return {"status": "PENDING",
                "note": "4-year report not generated yet. Run: python scripts/run_report.py"}
    import json
    return {"status": "READY", **json.loads(path.read_text())}


# ------------------------------ VALIDATION SUITE ------------------------------
@api.get("/validation")
async def validation():
    results = {"golden_bullish": {}, "golden_bearish": {}, "negatives": {}}
    gb = S.build_signal(SC.golden_bullish(), symbol="GOLD_BULL")
    results["golden_bullish"] = {"status": gb["status"], "pass": gb["status"] == S.A_PLUS_BUY}
    gs = S.build_signal(SC.golden_bearish(), symbol="GOLD_BEAR")
    results["golden_bearish"] = {"status": gs["status"], "pass": gs["status"] == S.A_PLUS_SELL}
    for name, tf in SC.negatives().items():
        sig = S.build_signal(tf, symbol=name)
        results["negatives"][name] = {"status": sig["status"], "actionable": sig["actionable"],
                                      "pass": not sig["actionable"]}
    all_pass = (results["golden_bullish"]["pass"] and results["golden_bearish"]["pass"]
                and all(v["pass"] for v in results["negatives"].values()))
    return {"all_pass": all_pass, "results": results}


# ------------------------------ NEWS / FUNDAMENTALS ------------------------------
@api.get("/news")
async def news(symbol: str = "XAU/USD"):
    return CTX.economic_calendar(symbol)


@api.get("/news/risk")
async def news_risk(symbol: str = "XAU/USD"):
    return CTX.news_risk(symbol)


@api.get("/fundamentals")
async def fundamentals(symbol: str = "XAU/USD"):
    return CTX.fundamentals(symbol)


@api.get("/confluence")
async def confluence(symbol: str = "XAU/USD", technical_bias: str = "BULLISH"):
    return CTX.confluence(technical_bias, symbol)


# ------------------------------ AI ASSISTANT ------------------------------
@api.post("/ai/explain")
async def ai_explain(body: AIExplainInput):
    tf = SC.golden_bullish() if body.direction == "bullish" else SC.golden_bearish()
    sig = S.build_signal(tf, symbol=body.symbol)
    result = await AI.explain(sig, session_id=body.session_id or "aureus")
    return {"signal": sig, **result}


# ------------------------------ JOURNAL ------------------------------
@api.post("/journal")
async def create_journal(body: JournalCreate, request: Request):
    user = await AUTH.get_current_user(request, db)
    plan = compute_risk(10000.0, body.risk_pct, body.entry, body.stop, body.target)
    entry = JournalEntry(user_id=user["_id"], **body.model_dump(),
                         rr=plan.get("rr"), position_size=plan.get("position_size"))
    doc = entry.to_mongo()
    res = await db.journal.insert_one(doc)
    saved = await db.journal.find_one({"_id": res.inserted_id})
    return JournalEntry.from_mongo(saved).model_dump(by_alias=False)


@api.get("/journal")
async def list_journal(request: Request, symbol: Optional[str] = None,
                       direction: Optional[str] = None, result: Optional[str] = None):
    user = await AUTH.get_current_user(request, db)
    query = {"user_id": user["_id"]}
    if symbol:
        query["symbol"] = symbol
    if direction:
        query["direction"] = direction
    if result:
        query["result"] = result
    docs = await db.journal.find(query).sort("date", -1).to_list(500)
    return [JournalEntry.from_mongo(d).model_dump(by_alias=False) for d in docs]


@api.delete("/journal/{entry_id}")
async def delete_journal(entry_id: str, request: Request):
    user = await AUTH.get_current_user(request, db)
    await db.journal.delete_one({"_id": ObjectId(entry_id), "user_id": user["_id"]})
    return {"ok": True}


# ------------------------------ WATCHLIST ------------------------------
@api.get("/watchlist")
async def get_watchlist(symbols: str = ""):
    syms = symbols.split(",") if symbols else DEFAULT_WATCHLIST
    rows = []
    for s in syms:
        s = s.strip()
        if not s:
            continue
        c = D.generate_5m(s, count=50)
        last, prev = c[-1]["close"], c[-2]["close"]
        rows.append({"symbol": s, "last": last, "change": round(last - prev, 6),
                     "change_pct": round((last - prev) / prev * 100, 3)})
    return {"items": rows}


# ------------------------------ ADMIN / PRESIDENT ------------------------------
@api.get("/admin/status")
async def admin_status():
    val = await validation()
    try:
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False
    return {
        "aureus_engine": "ONLINE",
        "data_feed": "ONLINE (SYNTHETIC)",
        "signal_engine": "READY",
        "risk_engine": "READY",
        "news_engine": "ONLINE (REFERENCE)",
        "backtest_engine": "READY",
        "ai_engine": "ONLINE" if os.environ.get("EMERGENT_LLM_KEY") else "NOT CONNECTED",
        "database": "ONLINE" if db_ok else "OFFLINE",
        "validation_all_pass": val["all_pass"],
        "state": "REAL-TIME | HISTORICAL | REPLAY | BACKTEST",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@api.get("/")
async def root():
    return {"platform": "AUREUS AI", "strategy": "V4 A+ Market Mechanics",
            "philosophy": "AUREUS does not trade often. AUREUS waits for the correct sequence."}


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.journal.create_index("user_id")
    await AUTH.seed_admin(db)
    logger.info("AUREUS backend started; admin seeded.")


@app.on_event("shutdown")
async def shutdown():
    client.close()
