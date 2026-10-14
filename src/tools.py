"""Pydantic tool schemas + implementations. The MCP server (mcp/mcp_tool_server.py) wraps these
same functions, and the orchestrator validates inputs with the same models before calling MCP."""
import json
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import corpus, settings

District = Literal["New Cairo", "Sheikh Zayed", "6th of October", "Maadi", "North Coast"]
PropType = Literal["apartment", "villa", "townhouse"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchListingsInput(_Strict):
    district: Optional[District] = None
    property_type: Optional[PropType] = None
    bedrooms: Optional[int] = Field(None, ge=1, le=10, description="Exact number of bedrooms")
    min_price_egp: Optional[int] = Field(None, ge=0, le=200_000_000)
    max_price_egp: Optional[int] = Field(None, gt=0, le=200_000_000)
    limit: int = Field(5, ge=1, le=10)


class FetchListingInput(_Strict):
    listing_id: str = Field(..., pattern=r"^LST-\d{3}$")


class MortgageInput(_Strict):
    price_egp: int = Field(..., gt=0, le=200_000_000)
    annual_rate_pct: float = Field(..., gt=0, le=40)
    years: int = Field(..., ge=1, le=30)
    down_payment_pct: float = Field(..., ge=0, le=90)


class ScheduleViewingInput(_Strict):
    listing_id: str = Field(..., pattern=r"^LST-\d{3}$")
    client_id: str = Field(..., pattern=r"^CLT-\d{3}$")
    date: date
    time: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    notes: Optional[str] = Field(None, max_length=200)

    @field_validator("date")
    @classmethod
    def _future(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("date must be today or later")
        return v


def search_listings(a: SearchListingsInput) -> dict:
    rows = []
    for l in corpus.load_listings().values():
        if a.district and l["district"] != a.district: continue
        if a.property_type and l["property_type"] != a.property_type: continue
        if a.bedrooms and l["bedrooms"] != a.bedrooms: continue
        if a.min_price_egp and l["price_egp"] < a.min_price_egp: continue
        if a.max_price_egp and l["price_egp"] > a.max_price_egp: continue
        rows.append(l)
    rows.sort(key=lambda r: r["price_egp"])
    return {"count": len(rows), "results": rows[: a.limit]}


def fetch_listing(a: FetchListingInput) -> dict:
    l = corpus.load_listings().get(a.listing_id)
    return {"found": bool(l), "listing": l}


def mortgage_calculator(a: MortgageInput) -> dict:
    down = a.price_egp * a.down_payment_pct / 100
    loan = a.price_egp - down
    r, n = a.annual_rate_pct / 100 / 12, a.years * 12
    monthly = loan * r / (1 - (1 + r) ** -n)
    return {"price_egp": a.price_egp, "down_payment_egp": round(down), "loan_amount_egp": round(loan),
            "monthly_payment_egp": round(monthly), "total_paid_egp": round(monthly * n + down),
            "total_interest_egp": round(monthly * n - loan), "rate_pct": a.annual_rate_pct,
            "years": a.years, "down_pct": a.down_payment_pct}


def schedule_viewing(a: ScheduleViewingInput) -> dict:
    if a.listing_id not in corpus.load_listings():
        return {"status": "rejected", "reason": f"unknown listing {a.listing_id}"}
    f = settings.VIEWINGS_FILE
    f.parent.mkdir(parents=True, exist_ok=True)
    bookings = json.loads(f.read_text()) if f.exists() else []
    if any(b["listing_id"] == a.listing_id and b["date"] == a.date.isoformat() and b["time"] == a.time for b in bookings):
        return {"status": "conflict", "reason": "slot already booked"}
    b = {"booking_id": f"VW-{len(bookings) + 1:04d}", "listing_id": a.listing_id, "client_id": a.client_id,
         "date": a.date.isoformat(), "time": a.time, "notes": a.notes}
    bookings.append(b)
    f.write_text(json.dumps(bookings, indent=2))
    return {"status": "confirmed", **b}


TOOLS = {
    "search_listings": (SearchListingsInput, search_listings),
    "fetch_listing": (FetchListingInput, fetch_listing),
    "mortgage_calculator": (MortgageInput, mortgage_calculator),
    "schedule_viewing": (ScheduleViewingInput, schedule_viewing),
}
