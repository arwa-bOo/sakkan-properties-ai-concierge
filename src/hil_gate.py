"""Human-in-the-Loop gate. Uses LangGraph interrupt(): the graph PAUSES here and nothing client-facing
is returned until the broker answers Approve / Reject / Edit. Cannot be disabled (see RAI config)."""
from langgraph.types import interrupt

ACTIONS = ("approve", "reject", "edit")


def build_review_payload(state: dict) -> dict:
    return {"channel": state.get("channel", "whatsapp"), "client": state.get("client_name", "client"),
            "language": state.get("language", "en"), "draft": state["draft"],
            "sources": state.get("sources", []), "trace_id": state["trace_id"]}


def request_approval(payload: dict) -> dict:
    """Pause the graph. The caller resumes it with Command(resume={'action': ..., 'text': ...})."""
    decision = interrupt(payload)
    if not isinstance(decision, dict) or decision.get("action") not in ACTIONS:
        return {"action": "reject", "reason": "invalid decision"}          # fail closed
    if decision["action"] == "edit" and not (decision.get("text") or "").strip():
        return {"action": "reject", "reason": "empty edit"}
    return decision


def apply_decision(draft: str, decision: dict) -> tuple[str | None, str]:
    """-> (text allowed to leave the office or None, status)."""
    if decision["action"] == "approve":
        return draft, "approved"
    if decision["action"] == "edit":
        return decision["text"].strip(), "edited"
    return None, "rejected"
