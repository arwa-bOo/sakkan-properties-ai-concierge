"""Draws docs/architecture.png."""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

fig, ax = plt.subplots(figsize=(13, 7.2)); ax.axis("off"); ax.set_xlim(0, 13); ax.set_ylim(0, 7.2)

def box(x, y, w, h, text, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.04,rounding_size=0.12", fc=color, ec="#333", lw=1.2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)

def arrow(a, b, style="->"):
    ax.annotate("", xy=b, xytext=a, arrowprops=dict(arrowstyle=style, lw=1.3, color="#333"))

box(0.2, 5.9, 2.4, 0.9, "Broker\n(Chainlit UI, cl.Step per event)", "#dbeafe")
box(3.3, 5.9, 2.2, 0.9, "1  Triage agent\n(intent · client · params)", "#fde68a")
box(6.2, 5.9, 2.6, 0.9, "2  Property finder\n(mem0 read · RAG · tools)", "#fde68a")
box(9.5, 5.9, 2.6, 0.9, "3  Mortgage analyst\n(MCP calculator · bank sheets)", "#fde68a")
box(9.5, 4.2, 2.6, 0.9, "4  Comms agent\n(AR/EN draft + ID check)", "#fde68a")
box(6.2, 4.2, 2.6, 0.9, "5  HiL gate (interrupt)\nApprove · Edit · Reject", "#fecaca")
box(3.3, 4.2, 2.2, 0.9, "6  Viewing scheduler\n(only after approval)", "#fde68a")
box(0.2, 4.2, 2.4, 0.9, "Final reply + Sources\n+ memory consent (Yes/No)", "#dbeafe")
for a, b in [((2.6, 6.35), (3.3, 6.35)), ((5.5, 6.35), (6.2, 6.35)), ((8.8, 6.35), (9.5, 6.35)), ((10.8, 5.9), (10.8, 5.1)),
             ((9.5, 4.65), (8.8, 4.65)), ((6.2, 4.65), (5.5, 4.65)), ((3.3, 4.65), (2.6, 4.65))]:
    arrow(a, b)
box(0.2, 2.5, 3.6, 0.95, "LangGraph state graph + MemorySaver\nstep counter · per-agent & per-run tool limits\n→ Fallback node (explicit uncertainty)", "#e9d5ff")
box(4.2, 2.5, 2.6, 0.95, "MCP tool server (stdio)\nsearch · fetch listing\nmortgage calc · schedule viewing", "#bbf7d0")
box(7.2, 2.5, 2.6, 0.95, "Qdrant  `sakkan_properties`\n60 docs · Gemini embeddings\ntop-4 + passage IDs", "#bbf7d0")
box(10.2, 2.5, 2.6, 0.95, "mem0 (self-hosted)\npreference · deal · episodic\nconsent-gated · /forget", "#bbf7d0")
box(0.2, 0.6, 12.6, 1.0, "observability.py — one trace_id per request → structlog JSON lines (trace_logs.jsonl)\n"
    "agent transitions · tool calls · retrievals · memory ops · HiL decisions\n"
    "RAI_Config.yaml: accuracy · tone · escalation · privacy · human review   |   DeepEval: Faithfulness · Consent · HiL · tool presence", "#f3f4f6")
for x in (2.0, 5.5, 8.5, 11.5):
    arrow((x, 2.5), (x, 4.15) if x < 3 else (x, 5.85), "<->") if False else None
ax.text(6.5, 7.0, "Sakkan Properties — Real-Estate AI Concierge", ha="center", fontsize=14, weight="bold")
Path(__file__).resolve().parent.parent.joinpath("docs").mkdir(exist_ok=True)
fig.savefig(Path(__file__).resolve().parent.parent / "docs" / "architecture.png", dpi=130, bbox_inches="tight")
print("saved docs/architecture.png")
