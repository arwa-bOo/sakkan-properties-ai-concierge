"""Runs one eval case through the real graph (auto Approve/Reject/Edit + auto consent) and scores it."""
import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path

from src import corpus
from src.memory import get_memory
from src.orchestrator import run_request

CASES = [json.loads(l) for l in (Path(__file__).parent / "eval_cases.jsonl").read_text("utf-8").splitlines() if l.strip()]
ID_RE = re.compile(r"\b(?:LST|CLT|AREA|MORT|SOP)-\d{3}\b")


def run_case(case: dict) -> dict:
    for s in case.get("seed_memory", []):                       # fixture data only, clearly separate from the UI consent path
        get_memory().add(s["client_id"], s["text"], s["kind"], consent=True)
    text = case["input"].replace("{{DATE+10}}", (date.today() + timedelta(days=10)).isoformat())

    def hil(payload):
        return {"action": case["hil"], "text": case.get("edit_text", "")}

    state = asyncio.run(run_request(text, hil_decider=hil, consent_decider=lambda c: bool(case.get("consent"))))
    ev = state["events"]
    called = [e["tool"] for e in ev if e["kind"] == "tool_call"]
    draft_text = (state.get("hil") or {}).get("final_text")
    listings = state.get("listings", [])
    context = [l["description"] + f" ID {l['id']} price {l['price_egp']:,} EGP, {l['bedrooms']} bedrooms, {l['district']}." for l in listings]
    context += [p["text"] for p in state.get("passages", [])]
    if state.get("mortgage"):
        context.append("Mortgage results: " + json.dumps(state["mortgage"].get("results", {})))
    return {"case": case, "state": state, "called": called, "draft": state.get("draft"), "final_text": draft_text,
            "reply": state["final_reply"], "context": context or ["(no retrieved context)"], "events": ev}


# ---------------------------------------------------------------- deterministic scores (always computed)
def faithfulness_det(r: dict) -> float:
    """Every listing ID mentioned anywhere in the reply/draft must exist in the corpus AND have been retrieved this run."""
    mentioned = set(re.findall(r"LST-\d{3}", (r["draft"] or "") + " " + r["reply"]))
    real = set(corpus.load_listings())
    retrieved = {l["id"] for l in r["state"].get("listings", [])} | {p["id"] for p in r["state"].get("passages", [])}
    if not mentioned:
        return 1.0 if r["state"].get("no_match") or not r["state"].get("plan", {}).get("needs_search") else 0.0
    return len(mentioned & real & retrieved) / len(mentioned)


def provenance_ok(r: dict) -> bool:
    return any(i in corpus.all_doc_ids() for i in ID_RE.findall(r["reply"]))


def consent_det(r: dict) -> float:
    granted = bool(r["case"].get("consent"))
    return 1.0 if (r["state"]["memory_written"] == 0 or granted) else 0.0


def hil_det(r: dict) -> float:
    st = r["state"]
    if not st.get("draft"):
        return 1.0 if "✅" not in r["reply"] else 0.0          # no draft -> nothing may be presented as 'approved'
    status = (st.get("hil") or {}).get("status")
    if status is None:
        return 0.0                                              # a draft existed but never passed the gate
    if status == "rejected":
        return 1.0 if st["draft"] not in r["reply"] else 0.0
    if status == "edited":
        return 1.0 if r["case"]["edit_text"] in r["reply"] else 0.0
    return 1.0 if st["draft"] in r["reply"] else 0.0


def tools_ok(r: dict) -> bool:
    return set(r["case"]["expect"].get("tools", [])) <= set(r["called"])


def expectations_ok(r: dict) -> list[str]:
    """Extra case-specific assertions; returns a list of failures."""
    e, st, fails = r["case"]["expect"], r["state"], []
    if "hil_triggered" in e and bool(st.get("hil")) != e["hil_triggered"]: fails.append("hil_triggered")
    if e.get("no_match") and not st.get("no_match"): fails.append("no_match")
    if e.get("no_match") and re.search(r"LST-\d{3}", r["draft"] or ""): fails.append("fabricated listing in no-match draft")
    if e.get("validation_recovered") and not any(x["kind"] == "validation_recovered" for x in r["events"]): fails.append("validation_recovered")
    if e.get("hil_status") and (st.get("hil") or {}).get("status") != e["hil_status"]: fails.append("hil_status")
    if "memory_written" in e and st["memory_written"] != e["memory_written"]: fails.append("memory_written")
    if e.get("booking") and (st.get("booking") or {}).get("result", {}).get("status") != "confirmed": fails.append("booking")
    for i in e.get("must_cite", []):
        if i not in (r["draft"] or "") + r["reply"]: fails.append(f"must_cite {i}")
    if e.get("must_cite_prefix") and not any(s.startswith(e["must_cite_prefix"]) for s in st.get("sources", [])): fails.append("must_cite_prefix")
    if e.get("language") and st.get("language") != e["language"]: fails.append("language")
    if not provenance_ok(r): fails.append("provenance (no doc ID cited)")
    return fails
