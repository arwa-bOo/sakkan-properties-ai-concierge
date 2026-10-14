"""CLI version of the anchor scenario (auto-approves). Handy to produce a clean outputs/trace_logs.jsonl.
Usage: python scripts/demo_run.py"""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src.orchestrator import run_request  # noqa: E402

REQ = ("Find Mr. Hassan three apartments in New Cairo under 5M EGP with 3 bedrooms, calculate his mortgage at 18% over 15 years "
       "with a 30% down payment, draft him a WhatsApp message in Arabic with the shortlist, and don't send anything until I approve.")


async def main():
    r = await run_request(REQ, hil_decider=lambda p: (print("\n--- HiL gate (auto-approve in CLI demo) ---\n" + p["draft"]) or {"action": "approve"}),
                          consent_decider=lambda c: False)
    print("\n" + r["final_reply"] + f"\n\ntrace_id={r['trace_id']} steps={r['steps']} tool_calls={r['tool_calls']}")

asyncio.run(main())
