# Sakkan Properties — Real-Estate AI Concierge (Agentic AI Capstone)

LangGraph multi-agent orchestration · Qdrant RAG · mem0 memory · MCP tools · Human-in-the-Loop · DeepEval · Chainlit.
A broker chats; agents filter listings, compute mortgages and draft Arabic/English messages — **nothing client-facing leaves without the broker's Approve / Edit / Reject.** Cost: **$0**.

![architecture](docs/architecture.png)

## Quick Start (5 commands)
```bash
git clone <your-repo-url> sakkan-properties-ai-concierge && cd sakkan-properties-ai-concierge
python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cp .env.example .env            # paste your free GEMINI_API_KEY (aistudio.google.com). No key? set MOCK_MODE=true
python -m src.ingest_qdrant     # embeds the 60 docs into Qdrant collection `sakkan_properties` (<1 min)
chainlit run app.py             # http://localhost:8000
```
Qdrant runs **embedded** (folder `.qdrant_local/`) by default — no Docker. For Qdrant Cloud (free tier) or `docker compose up -d`, set `QDRANT_URL` / `QDRANT_API_KEY` in `.env`.

**Demo prompt** (anchor scenario):
> Find Mr. Hassan three apartments in New Cairo under 5M EGP with 3 bedrooms, calculate his mortgage at 18% over 15 years with a 30% down payment, draft him a WhatsApp message in Arabic with the shortlist, and don't send anything until I approve.

Chat commands: `/forget CLT-001` (deletes that client's memory, prints the count only) · `/remember CLT-001 preference <text>` (consent gate) · `/help`.

## What happens on a request
1. **Triage** → intent, client (CLT-xxx), language, filters, mortgage terms · 2. **Property finder** → mem0 read, Qdrant top-4 RAG, MCP `search_listings`/`fetch_listing` · 3. **Mortgage analyst** → MCP `mortgage_calculator` + bank-sheet check · 4. **Comms** → AR/EN draft, validated against retrieved listing IDs · 5. **HiL gate** (LangGraph `interrupt`) · 6. **Viewing scheduler** (side effect only *after* approval) · then a **memory consent** prompt (Yes/No).
Tool-call limits (4/agent, 10/run) and a 12-step cap route to a **fallback** that answers with explicit uncertainty.

## Repo map
| Path | Role |
|---|---|
| `app.py` | Chainlit UI, one `cl.Step` per agent/tool/retrieval/memory/HiL event |
| `src/orchestrator.py` | LangGraph state graph, routing, limits, fallback, headless runner |
| `src/agents/` | triage · property_finder · mortgage_analyst · comms |
| `src/tools.py`, `mcp/mcp_tool_server.py`, `src/mcp_client.py` | Pydantic schemas, MCP server (4 tools), MCP client |
| `src/rag_chain.py`, `src/ingest_qdrant.py` | Qdrant retrieval / ingestion |
| `src/memory.py` | mem0: preference · deal · episodic, consent-gated, per-client forget |
| `src/hil_gate.py`, `src/observability.py`, `src/node_context.py` | HiL logic, trace_id + structlog, tool runner + limits |
| `tests/` | DeepEval suite (`test_agent.py`, `eval_cases.jsonl`) + unit tests |
| `config/RAI_Config.yaml` | Responsible-AI rules |
| `scripts/reset.sh` | wipe Qdrant + mem0 and re-ingest in one command |

## Tests & evaluation
```bash
pytest tests -q                 # 10 DeepEval cases + 6 unit tests -> outputs/eval_report.json
MOCK_MODE=true pytest tests -q  # offline: deterministic scorers only
```
With a Gemini key the suite runs `FaithfulnessMetric` + `GEval(ConsentRespect)` + `GEval(HiLRespect)` (Gemini as judge) **and** the deterministic checks; a case passes only if both agree. Stop the Chainlit app before running tests in embedded-Qdrant mode (the local store allows one process at a time).

## Notes
- `mcp/` has no `__init__.py` on purpose so it never shadows the installed `mcp` SDK. Keep `mcp<2` (v2 renamed `FastMCP`).
- Memory content is never written to trace logs (IDs/counts only). `outputs/viewings.json` is the mock calendar.
- Switching between MOCK and live mode changes embeddings: run `scripts/reset.sh` after switching.
- **Demo:** `docs/demo.mp4` (65 s, recorded in MOCK_MODE) shows the Hassan scenario end-to-end: triage → finder (mem0, RAG, MCP) → mortgage → comms → HiL Approve → memory consent → `/forget`. Screenshots: `docs/chainlit_steps.png`, `docs/approved_message.png`.
- **Live Gemini:** with `MOCK_MODE=false` the triage/comms/answer agents call Gemini (`GEMINI_MODEL`, default `gemini-flash-latest`). If a model returns 404 the system falls back to the deterministic template instead of crashing; set another model name in `.env`.
