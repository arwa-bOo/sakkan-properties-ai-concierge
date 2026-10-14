"""Mortgage analyst agent: runs the MCP mortgage_calculator for each shortlisted listing and
checks which fictional bank sheets (MORT-xxx) allow the requested tenure / down payment."""
from .. import corpus
from ..node_context import BudgetExceeded, NodeContext

DEFAULTS = {"rate_pct": 18.0, "years": 15, "down_pct": 30.0}


async def mortgage_analyst_node(state: dict) -> dict:
    ctx = NodeContext(state, "mortgage_analyst")
    plan = state["plan"]
    terms = {k: plan.get(k) if plan.get(k) is not None else v for k, v in DEFAULTS.items()}
    assumptions = [f"{k} not given, assumed {v}" for k, v in DEFAULTS.items() if plan.get(k) is None]
    ctx.emit("agent_transition", agent="mortgage_analyst", detail=f"rate {terms['rate_pct']}% / {terms['years']}y / {terms['down_pct']}% down")
    prices = [(l["id"], l["price_egp"]) for l in state.get("listings", [])[:3]]
    if not prices and plan.get("max_price_egp") and not state.get("no_match"):
        prices = [("budget", plan["max_price_egp"])]
    results = {}
    try:
        for ref, price in prices:
            args = {"price_egp": price, "annual_rate_pct": terms["rate_pct"], "years": terms["years"], "down_payment_pct": terms["down_pct"]}
            r = await ctx.call("mortgage_calculator", args)
            if not r["ok"]:                                   # feedback already logged as tool_error; skip this listing
                continue
            results[ref] = r["result"]
        banks = [b for b in corpus.load_banks() if terms["years"] <= b["max_tenure"] and terms["down_pct"] >= b["min_down"]]
        ctx.emit("agent_transition", agent="mortgage_analyst", detail=f"{len(results)} calculation(s); {len(banks)} bank sheet(s) fit",
                 banks=[b["id"] for b in banks])
        sources = list(dict.fromkeys(list(state.get("sources", [])) + [b["id"] for b in banks]))
        return ctx.update(mortgage={"terms": terms, "results": results, "assumptions": assumptions, "banks_fit": banks}, sources=sources)
    except BudgetExceeded as e:
        return ctx.overflow(e)
