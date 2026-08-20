from datetime import datetime, timezone
from typing import Annotated, Any, Optional, List
from bson import ObjectId
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict, EmailStr


def _to_str_objectid(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    return str(v)


PyObjectId = Annotated[str, BeforeValidator(_to_str_objectid)]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        if not doc:
            return None
        doc = dict(doc)
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return cls(**doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        data.pop("id", None)
        return data


# ---------- Auth ----------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = "Trader"


class LoginInput(BaseModel):
    email: EmailStr
    password: str


# ---------- Journal ----------
class JournalEntry(BaseDocument):
    user_id: Optional[str] = None
    symbol: str
    direction: str
    date: str = Field(default_factory=utcnow_iso)
    entry: float
    stop: float
    target: float
    risk_pct: float = 1.0
    position_size: Optional[float] = None
    rr: Optional[float] = None
    result: str = "open"           # open / win / loss / breakeven
    r_result: Optional[float] = None
    setup_type: str = "V4 A+"
    timeframe: str = "M5"
    market_context: Optional[str] = None
    aureus_conditions: Optional[dict] = None
    user_notes: Optional[str] = None
    execution_notes: Optional[str] = None
    emotion_notes: Optional[str] = None
    chart_reference: Optional[str] = None


class JournalCreate(BaseModel):
    symbol: str
    direction: str
    entry: float
    stop: float
    target: float
    risk_pct: float = 1.0
    result: str = "open"
    setup_type: str = "V4 A+"
    timeframe: str = "M5"
    market_context: Optional[str] = None
    user_notes: Optional[str] = None
    execution_notes: Optional[str] = None
    emotion_notes: Optional[str] = None


# ---------- Watchlist ----------
class WatchlistItem(BaseModel):
    symbol: str
    name: str = ""
    asset_class: str = "forex"


# ---------- Requests ----------
class RiskInput(BaseModel):
    equity: float = 10000.0
    risk_pct: float = 1.0
    entry: float
    stop: float
    target: float
    asset_class: str = "forex"


class AIExplainInput(BaseModel):
    symbol: str = "XAU/USD"
    direction: str = "bullish"
    session_id: Optional[str] = None
