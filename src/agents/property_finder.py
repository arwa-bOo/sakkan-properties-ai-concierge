"""Property finder agent: mem0 read -> Qdrant RAG (top-4) -> MCP search_listings / fetch_listing.
Recovers from Pydantic validation errors by repairing the arguments from the error feedback."""
import asyncio
import re

from ..memory import get_memory
from ..node_context import BudgetExceeded, NodeContext
from ..rag_chain import retrieve


def repair_args(args: dict, details: list[dict]) -> dict:
    """Turn validation feedback into a corrected call: clamp numeric bounds, drop invalid values."""
    fixed = dict(args)
    for d in details:
        f = d["field"].split(".")[0]
        if f not in fixed:
            continue
        ctx = d.get("ctx") or {}
        for bound in ("le", "lt", "ge", "gt"):
            if bound in ctx and isinstance(fixed[f], (int, float)):
                fixed[f] = ctx[bound] if bound in ("le", "ge") else ctx[bound] + (-1 if bound == "lt" else 1)
                break
        else:
            fixed.pop(f)
    return fixed


async def _search_with_recovery(ctx: NodeContext, args: dict) -> dict | None:
    res = await ctx.call("search_listings", args)
    if res["ok"]:
        return res["result"]
    fixed = repair_args(args, res["details"])
    ctx.emit("validation_recovered", tool="search_listings", original=args, repaired=fixed)
    res2 = await ctx.call("search_listings", fixed)
    return res2["result"] if res2["ok"] else None


async def property_finder_node(state: dict) -> dict:
    ctx = NodeContext(state, "property_finder")
    plan, cid = state["plan"], state.get("client_id")
    ctx.emit("agent_transition", agent="property_finder", detail="memory read -> RAG -> listing tools")
    out: dict = {}
    try:
        memories = []
        if cid:
            memories = await asyncio.to_thread(get_memory().read, cid, state["request"])
            ctx.emit("memory_read", client_id=cid, count=len(memories), items=[{"kind": m["kind"], "text": m["text"]} for m in memories])
        prefs = " ".join(m["text"] for m in memories if m["kind"] == "preference")
        query = " ".join(x for x in [state["request"], prefs] if x)[:500]
        passages = await asyncio.to_thread(retrieve, query)
        # privacy: another client's brief must never surface in this client's run
        passages = [p for p in passages if p["doc_type"] != "client_brief" or p["id"] == cid]
        ctx.emit("retrieval", query=query, passages=[{"id": p["id"], "doc_type": p["doc_type"], "score": p["score"], "snippet": p["text"][:140]} for p in passages])
        rag_ids = [p["id"] for p in passages]

        listings: list[dict] = []
        ids = list(plan["listing_ids"])
        if not ids and plan["intent"] == "draft_message" and not plan.get("max_price_egp") and not plan.get("bedrooms"):
            deal_ids = [i for m in memories if m["kind"] == "deal" for i in re.findall(r"LST-\d{3}", m["text"])]
            ids = list(dict.fromkeys(deal_ids))        # "the villa we shortlisted last week" -> from the deal memory
        for lid in ids[:3]:
            r = await ctx.call("fetch_listing", {"listing_id": lid})
            if r["ok"] and r["result"]["found"]:
                l = r["result"]["listing"]
                if (not plan["district"] or l["district"] == plan["district"]) and (not plan["property_type"] or l["property_type"] == plan["property_type"]):
                    listings.append(l)
        no_match = False
        if not listings and plan["needs_search"]:
            args = {k: plan[k] for k in ("district", "property_type", "bedrooms", "max_price_egp") if plan.get(k)}
            args["limit"] = 10
            found = await _search_with_recovery(ctx, args)
            cands = (found or {}).get("results", [])
            cands.sort(key=lambda l: (l["id"] not in rag_ids, l["price_egp"]))      # RAG hits (e.g. near schools) first
            listings = cands[: plan["count"]]
            no_match = not listings
            if no_match:
                ctx.emit("no_match", detail="no listing in the corpus matches the filters")
        extra = [i for i in rag_ids if not i.startswith("LST-") or i in {l["id"] for l in listings}]
        sources = list(dict.fromkeys([l["id"] for l in listings] + extra))[:6] or rag_ids[:3]
        out = dict(listings=listings, passages=passages, memories=memories, no_match=no_match, sources=sources)
        ctx.emit("agent_transition", agent="property_finder", detail=f"{len(listings)} listing(s) selected", listing_ids=[l["id"] for l in listings])
        return ctx.update(**out)
    except BudgetExceeded as e:
        return ctx.overflow(e, listings=out.get("listings", []), sources=out.get("sources", []))
