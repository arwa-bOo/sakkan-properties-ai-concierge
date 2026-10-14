"""Chainlit UI for the Sakkan Properties AI Concierge.
Every agent, MCP tool call, retrieval, memory read and HiL decision is rendered as a visible cl.Step.
Run:  chainlit run app.py   ->  http://localhost:8000"""
import json

import chainlit as cl
from langgraph.types import Command

from src import settings
from src.memory import KINDS, get_memory
from src.observability import make_event, new_trace_id
from src.orchestrator import build_graph, initial_state, pending_interrupt

NODE_LABEL = {"triage": "🧭 Triage agent", "property_finder": "🏠 Property finder agent", "mortgage_analyst": "💰 Mortgage analyst agent",
              "comms": "✍️ Communication agent", "hil_gate": "🛑 Human-in-the-Loop gate", "book_viewing": "📅 Viewing scheduler",
              "respond": "💬 Responder", "fallback": "⚠️ Fallback (explicit uncertainty)"}
EVENT_META = {  # kind -> (label, cl.Step type)
    "agent_transition": ("Agent", "run"), "tool_call": ("🔧 MCP tool", "tool"), "tool_error": ("❗ Tool error (fed back to agent)", "tool"),
    "validation_recovered": ("♻️ Pydantic validation error recovered", "tool"), "retrieval": ("📚 RAG retrieval (Qdrant top-4)", "retrieval"),
    "memory_read": ("🧠 mem0 read", "retrieval"), "no_match": ("🚫 No matching listing", "run"), "draft_ready": ("📝 Draft ready for review", "run"),
    "hil_decision": ("🛑 HiL decision", "run"), "fallback": ("⚠️ Limit reached", "run"),
}
HELP = """**Sakkan Properties AI Concierge** — every client-facing draft waits for your approval.

Try: *Find Mr. Hassan three apartments in New Cairo under 5M EGP with 3 bedrooms, calculate his mortgage at 18% over 15 years with a 30% down payment, draft him a WhatsApp message in Arabic with the shortlist, and don't send anything until I approve.*

Commands: `/forget CLT-001` · `/remember CLT-001 preference <text>` (kinds: preference, deal, episodic) · `/help`
Mode: **{mode}**"""


def _js(x) -> str:
    return json.dumps(x, ensure_ascii=False, indent=2, default=str)


@cl.on_chat_start
async def start():
    cl.user_session.set("graph", build_graph())
    cl.user_session.set("broker_id", "broker-1")
    await cl.Message(HELP.format(mode="MOCK (offline stubs)" if settings.MOCK_MODE else f"live · {settings.GEMINI_MODEL}")).send()


async def render_events(parent: cl.Step, events: list[dict]):
    for ev in events:
        label, stype = EVENT_META.get(ev["kind"], (ev["kind"], "run"))
        if ev["kind"] == "tool_call":
            name = f"{label}: {ev['tool']}"
        elif ev["kind"] == "agent_transition":
            name = f"▶ {ev.get('detail') or ev.get('intent') or ev['agent']}"
        else:
            name = label
        async with cl.Step(name=name, type=stype, parent_id=parent.id, show_input="json") as s:
            body = {k: v for k, v in ev.items() if k not in ("trace_id", "kind", "agent")}
            s.input = _js(body.pop("input", "")) if "input" in body else ""
            s.output = _js(body.pop("output", body)) if "output" in body else _js(body)
            s.language = "json"


async def ask_hil(p: dict) -> dict:
    actions = [cl.Action(name="approve", payload={"a": "approve"}, label="✅ Approve"),
               cl.Action(name="edit", payload={"a": "edit"}, label="✏️ Edit"),
               cl.Action(name="reject", payload={"a": "reject"}, label="❌ Reject")]
    async with cl.Step(name="🛑 HiL gate: waiting for broker", type="run") as s:
        s.output = f"{p['channel']} → {p['client']} ({p['language']}) · sources: {', '.join(p['sources'])}"
    res = await cl.AskActionMessage(content=f"**Review before anything is sent** — {p['channel']} to {p['client']}\n\n```\n{p['draft']}\n```",
                                    actions=actions, timeout=3600, raise_on_timeout=False).send()
    choice = (res or {}).get("name", "reject")                 # timeout / no answer -> fail closed
    if choice == "edit":
        ans = await cl.AskUserMessage(content="Paste the edited message (it will be sent exactly as you write it):", timeout=3600, raise_on_timeout=False).send()
        return {"action": "edit", "text": (ans or {}).get("output", "")}
    return {"action": choice}


async def ask_consent(candidates: list[dict], trace_id: str):
    lines = "\n".join(f"- *{c['kind']}* · {c['text']}" for c in candidates)
    res = await cl.AskActionMessage(
        content=f"🧠 **Save to memory?** (client {candidates[0]['client_id']})\n\n{lines}\n\nNothing is stored unless you say Yes.",
        actions=[cl.Action(name="yes", payload={"v": True}, label="✅ Yes, save"), cl.Action(name="no", payload={"v": False}, label="🚫 No")],
        timeout=600, raise_on_timeout=False).send()
    granted = (res or {}).get("name") == "yes"
    n = get_memory().apply_consent(trace_id, candidates, granted, cl.user_session.get("broker_id"))
    await cl.Message(f"🧠 Memory: {n} item(s) saved." if granted else "🧠 Memory: nothing saved (consent not given).").send()


async def handle_command(text: str) -> bool:
    parts = text.split(maxsplit=3)
    cmd = parts[0].lower()
    if cmd == "/help":
        await cl.Message(HELP.format(mode="MOCK" if settings.MOCK_MODE else "live")).send()
    elif cmd == "/forget":
        if len(parts) < 2:
            await cl.Message("Usage: `/forget CLT-001`").send()
        else:
            try:
                n = get_memory().forget(parts[1].upper(), new_trace_id())
                await cl.Message(f"🗑️ Removed **{n}** memory entr{'y' if n == 1 else 'ies'} for {parts[1].upper()}. (Content is never echoed.)").send()
            except ValueError as e:
                await cl.Message(str(e)).send()
    elif cmd == "/remember":
        if len(parts) < 4 or parts[2].lower() not in KINDS:
            await cl.Message(f"Usage: `/remember CLT-001 <{'|'.join(KINDS)}> <text>`").send()
        else:
            await ask_consent([{"client_id": parts[1].upper(), "kind": parts[2].lower(), "text": parts[3]}], new_trace_id())
    else:
        return False
    return True


@cl.on_message
async def main(message: cl.Message):
    text = message.content.strip()
    if text.startswith("/") and await handle_command(text):
        return
    graph, broker = cl.user_session.get("graph"), cl.user_session.get("broker_id")
    state0 = initial_state(text, broker)
    trace_id = state0["trace_id"]
    config = {"configurable": {"thread_id": trace_id}}
    inputs = state0
    while True:
        async for chunk in graph.astream(inputs, config, stream_mode="updates"):
            for node, update in chunk.items():
                if node.startswith("__") or not update:
                    continue
                async with cl.Step(name=NODE_LABEL.get(node, node), type="run") as parent:
                    parent.output = f"{len(update.get('events', []))} event(s) · trace_id={trace_id}"
                    await render_events(parent, update.get("events", []))
        payload = await pending_interrupt(graph, config)
        if payload is None:
            break
        decision = await ask_hil(payload)
        inputs = Command(resume=decision)
    final = (await graph.aget_state(config)).values
    make_event(trace_id, "run_end", "orchestrator", steps=final.get("steps"), tool_calls=final.get("tool_calls"))
    await cl.Message(f"{final['final_reply'].replace(chr(10), '  ' + chr(10))}\n\n`trace_id: {trace_id}` · steps: {final.get('steps')} · tool calls: {final.get('tool_calls')}").send()
    if final.get("memory_candidates"):
        await ask_consent(final["memory_candidates"], trace_id)
