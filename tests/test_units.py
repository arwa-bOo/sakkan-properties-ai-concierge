"""Fast unit tests: validation, math, consent, forget, tool-call limits, max-steps fallback."""
import asyncio

import pytest
from pydantic import ValidationError

from src import settings, tools
from src.memory import get_memory
from src.orchestrator import run_request

REQ = "Find Mr. Hassan three apartments in New Cairo under 5M EGP with 3 bedrooms and draft a WhatsApp message in Arabic."


def test_mortgage_math():
    r = tools.mortgage_calculator(tools.MortgageInput(price_egp=4_500_000, annual_rate_pct=18, years=15, down_payment_pct=30))
    assert r["loan_amount_egp"] == 3_150_000 and r["monthly_payment_egp"] == 50_728


def test_strict_schema_rejects_bad_input():
    with pytest.raises(ValidationError):
        tools.SearchListingsInput(bedrooms=15)
    with pytest.raises(ValidationError):
        tools.SearchListingsInput(district="Atlantis")
    with pytest.raises(ValidationError):
        tools.FetchListingInput(listing_id="villa-1")


def test_memory_requires_consent_and_forget_reports_count_only():
    m = get_memory()
    assert m.add("CLT-007", "likes quiet streets", "preference", consent=False)["ok"] is False
    assert m.count("CLT-007") == 0
    assert m.add("CLT-007", "likes quiet streets", "preference", consent=True)["ok"]
    assert m.add("CLT-007", "viewing Saturday", "deal", consent=True)["ok"]
    assert m.add("CLT-008", "other client's note", "preference", consent=True)["ok"]
    assert m.forget("CLT-007") == 2 and m.count("CLT-007") == 0
    assert m.count("CLT-008") == 1                        # other clients untouched
    m.forget("CLT-008")


def test_tool_call_limit_routes_to_fallback(monkeypatch):
    monkeypatch.setattr(settings, "PER_AGENT_TOOL_LIMIT", 0)
    r = asyncio.run(run_request(REQ, hil_decider=lambda p: {"action": "approve"}))
    assert r["fallback_reason"] and "uncertainty" in r["final_reply"] and not r.get("draft")


def test_max_steps_routes_to_fallback(monkeypatch):
    monkeypatch.setattr(settings, "MAX_STEPS", 1)
    r = asyncio.run(run_request(REQ, hil_decider=lambda p: {"action": "approve"}))
    assert "max steps" in r["final_reply"] and not r.get("draft")


def test_no_decider_fails_closed():
    r = asyncio.run(run_request(REQ))                     # nobody answers the HiL gate -> reject
    assert r["hil"]["status"] == "rejected" and "Nothing was sent" in r["final_reply"]
