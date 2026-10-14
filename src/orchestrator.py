"""LangGraph multi-agent orchestrator.

 START -> triage -> property_finder -> [mortgage_analyst] -> [comms -> hil_gate -> [book_viewing]] | respond -> END
 any node  --(tool-limit / max-steps overflow)-->  fallback (explicit uncertainty)  -> END
"""
import asyncio
import operator
from typing import Annotated, Any, Callable, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from . import hil_gate, llm, prompts, settings
from .agents import comms_node, mortgage_analyst_node, property_finder_node, triage_node
from .memory import get_memory, propose_candidates
from .node_context import BudgetExceeded, NodeContext
from .observability import make_event, new_trace_id, redact


def _merge_counts(a: Optional[dict], b: Optional[dict]) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        out[k] = out.get(k, 0) + v
    return out


class State(TypedDict, total=False):
    trace_id: str
    broker_id: str
    request: str
    plan: dict
    client_id: Optional[str]
    client_name: Optional[str]
    language: str
    channel: Optional[str]
    listings: list
    passages: list
    memories: list
    mortgage: dict
    no_match: bool
    sources: list
    draft: str
    hil: dict
    booking: dict
    final_reply: str
    fallback_reason: Optional[str]
    memory_candidates: list
    events: Annotated[list, operator.add]
    tool_calls: Annotated[dict, _merge_counts]
    steps: Annotated[int, operator.add]


def _sources_line(state: dict) -> str:
    return "Sources: " + (", ".join(state.get("sources", [])) or "none retrieved")


# ------------------------------------------------------------------ nodes
async def hil_node(state: State) -> dict:
    ctx = NodeContext(state, "hil_gate")
    decision = hil_gate.request_approval(hil_gate.build_review_payload(state))   # <- graph pauses here
    text, status = hil_gate.apply_decision(state["draft"], decision)
    ctx.emit("hil_decision", decision=decision["action"], status=status, edited=status == "edited", chars=len(text or ""))
    if text is None:
        reply = f"❌ Draft rejected by the broker. Nothing was sent.\n\n{_sources_line(state)}"
    else:
        label = "approved" if status == "approved" else "edited and approved"
        reply = f"✅ Message {label} by the broker — ready to send via {state.get('channel')}:\n\n{text}\n\n{_sources_line(state)}"
    return ctx.update(hil={"status": status, "decision": decision["action"], "final_text": text}, final_reply=reply,
                      memory_candidates=propose_candidates(state, status))


async def book_viewing_node(state: State) -> dict:
    """Side effect only AFTER the broker approved the client message."""
    ctx = NodeContext(state, "viewing_scheduler")
    plan = state["plan"]
    ctx.emit("agent_transition", agent="viewing_scheduler", detail="booking after HiL approval")
    try:
        r = await ctx.call("schedule_viewing", {"listing_id": plan["listing_ids"][0], "client_id": state.get("client_id") or "",
                                                "date": plan.get("date") or "", "time": plan.get("time") or ""})
    except BudgetExceeded as e:
        return ctx.overflow(e)
    if r["ok"] and r["result"]["status"] == "confirmed":
        note = f"📅 Viewing booked: {r['result']['booking_id']} on {r['result']['date']} at {r['result']['time']}."
    else:
        why = r.get("details") or r.get("result", {}).get("reason", "unknown")
        note = f"⚠️ Viewing NOT booked ({redact(why, state.get('client_id'))}). Please fix the details and retry."
    return ctx.update(booking=r, final_reply=state["final_reply"] + "\n\n" + note)


async def respond_node(state: State) -> dict:
    """Internal (broker-only) answer: no client-facing text, so no HiL gate is needed."""
    ctx = NodeContext(state, "respond")
    plan = state["plan"]
    ctx.emit("agent_transition", agent="respond", detail=f"internal answer for intent '{plan['intent']}'")
    parts = []
    if plan["intent"] == "escalate":
        parts.append("⚠️ This request needs a senior broker (legal / negotiation / complaint). I did not draft anything.")
    elif plan["intent"] == "knowledge_question":
        top = state.get("passages", [])
        answer = None
        if not settings.MOCK_MODE and top:
            ctx_txt = "\n\n".join(f"[{p['id']}] {p['text']}" for p in top)
            try:
                answer = (await asyncio.to_thread(llm.generate, f"PASSAGES:\n{ctx_txt}\n\nQUESTION: {state['request']}", prompts.KNOWLEDGE_SYSTEM)).strip()
            except Exception as e:
                ctx.emit("tool_error", tool="gemini_answer", error=str(e)[:200])
        if not answer:
            best = top[0] if top else None
            answer = (f"[{best['id']}] {best['text'][:500]}" if best else "I could not find anything relevant in the corpus.")
        parts.append(answer)
        state_sources = [p["id"] for p in top]
        return ctx.update(final_reply=f"{answer}\n\nSources: {', '.join(state_sources)}", sources=state_sources,
                          memory_candidates=propose_candidates(state))
    elif plan["intent"] == "remember_note":
        parts.append(f"I can save this note for {state.get('client_name') or 'the client'}: “{plan['remember_text']}”. Nothing is stored until you consent.")
    if state.get("no_match"):
        parts.append("No listing in the corpus matches those filters. I will not invent one.")
    for l in state.get("listings", []):
        line = f"• [{l['id']}] {l['bedrooms']}BR {l['property_type']} – {l['compound']}, {l['district']} – EGP {l['price_egp']:,} ({l['finishing']})"
        m = (state.get("mortgage") or {}).get("results", {}).get(l["id"])
        if m:
            line += f"\n    ↳ monthly ≈ EGP {m['monthly_payment_egp']:,} ({m['down_pct']:g}% down, {m['rate_pct']:g}%, {m['years']}y)"
        parts.append(line)
    mort = state.get("mortgage") or {}
    if mort.get("results") and "budget" in mort["results"]:
        m = mort["results"]["budget"]
        parts.append(f"• Budget EGP {m['price_egp']:,}: monthly ≈ EGP {m['monthly_payment_egp']:,}, total interest EGP {m['total_interest_egp']:,}")
    if mort.get("assumptions"):
        parts.append("Assumptions: " + "; ".join(mort["assumptions"]))
    if mort.get("banks_fit"):
        parts.append("Bank sheets that allow these terms: " + ", ".join(f"{b['bank']} ({b['id']})" for b in mort["banks_fit"]))
    return ctx.update(final_reply="\n".join(parts) + f"\n\n{_sources_line(state)}", memory_candidates=propose_candidates(state))


async def fallback_node(state: State) -> dict:
    ctx = NodeContext(state, "fallback")
    reason = state.get("fallback_reason") or f"max steps ({settings.MAX_STEPS}) exceeded"
    ctx.emit("agent_transition", agent="fallback", detail=redact(reason, state.get("client_id")))
    have = [f"[{l['id']}] EGP {l['price_egp']:,}" for l in state.get("listings", [])]
    msg = ("I couldn't finish this request reliably, so I'm answering with uncertainty instead of guessing.\n"
           f"Reason: {redact(reason, state.get('client_id'))}.\n"
           + (f"What I verified so far: {'; '.join(have)}.\n" if have else "I have no verified listings for this request yet.\n")
           + "No client message was produced. Please narrow the request or continue manually.\n\n" + _sources_line(state))
    return ctx.update(final_reply=msg)


# ------------------------------------------------------------------ routing
def _guard(state: State) -> Optional[str]:
    if state.get("fallback_reason") or state.get("steps", 0) >= settings.MAX_STEPS:
        return "fallback"
    return None


def after_triage(state: State) -> str:
    return _guard(state) or ("respond" if state["plan"]["intent"] == "escalate" else "property_finder")


def after_finder(state: State) -> str:
    plan = state["plan"]
    return _guard(state) or ("mortgage_analyst" if plan["needs_mortgage"] else "comms" if plan["needs_draft"] else "respond")


def after_mortgage(state: State) -> str:
    return _guard(state) or ("comms" if state["plan"]["needs_draft"] else "respond")


def after_comms(state: State) -> str:
    return _guard(state) or "hil_gate"


def after_hil(state: State) -> str:
    ok = state.get("hil", {}).get("status") in ("approved", "edited")
    return "book_viewing" if ok and state["plan"]["intent"] == "schedule_viewing" else END


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("triage", triage_node), ("property_finder", property_finder_node), ("mortgage_analyst", mortgage_analyst_node),
                     ("comms", comms_node), ("hil_gate", hil_node), ("book_viewing", book_viewing_node),
                     ("respond", respond_node), ("fallback", fallback_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "triage")
    g.add_conditional_edges("triage", after_triage, ["property_finder", "respond", "fallback"])
    g.add_conditional_edges("property_finder", after_finder, ["mortgage_analyst", "comms", "respond", "fallback"])
    g.add_conditional_edges("mortgage_analyst", after_mortgage, ["comms", "respond", "fallback"])
    g.add_conditional_edges("comms", after_comms, ["hil_gate", "fallback"])
    g.add_conditional_edges("hil_gate", after_hil, ["book_viewing", END])
    for n in ("book_viewing", "respond", "fallback"):
        g.add_edge(n, END)
    return g.compile(checkpointer=checkpointer or MemorySaver())


def initial_state(request: str, broker_id: str = "broker-1", trace_id: Optional[str] = None) -> dict:
    tid = trace_id or new_trace_id()
    make_event(tid, "run_start", "orchestrator", request=request, broker_id=broker_id)
    return {"trace_id": tid, "broker_id": broker_id, "request": request, "events": [], "tool_calls": {}, "steps": 0}


async def pending_interrupt(graph, config) -> Optional[dict]:
    snap = await graph.aget_state(config)
    if snap.next and snap.tasks and snap.tasks[0].interrupts:
        return snap.tasks[0].interrupts[0].value
    return None


async def run_request(request: str, *, graph=None, broker_id: str = "broker-1",
                      hil_decider: Optional[Callable[[dict], dict]] = None,
                      consent_decider: Optional[Callable[[list], bool]] = None) -> dict:
    """Headless runner (tests, CLI demo). The Chainlit UI drives the same graph with live steps."""
    graph = graph or build_graph()
    state0 = initial_state(request, broker_id)
    config = {"configurable": {"thread_id": state0["trace_id"]}}
    result: Any = await graph.ainvoke(state0, config)
    while (payload := await pending_interrupt(graph, config)) is not None:
        decision = hil_decider(payload) if hil_decider else {"action": "reject"}     # no decider -> fail closed
        result = await graph.ainvoke(Command(resume=decision), config)
    cands = result.get("memory_candidates") or []
    written = 0
    if cands:
        granted = bool(consent_decider(cands)) if consent_decider else False
        written = get_memory().apply_consent(result["trace_id"], cands, granted, broker_id)
    result["memory_written"] = written
    make_event(result["trace_id"], "run_end", "orchestrator", steps=result.get("steps"), tool_calls=result.get("tool_calls"),
               memory_written=written, fallback=result.get("fallback_reason"))
    return result
