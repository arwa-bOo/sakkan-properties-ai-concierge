"""Per-node helper: event emission, tool calls through MCP, validation feedback, tool-call limits."""
from pydantic import ValidationError

from . import settings, tools
from .mcp_client import call_mcp_tool
from .observability import make_event


class BudgetExceeded(Exception):
    """Raised when a per-agent / per-run tool-call limit is hit -> graph routes to the fallback."""


class NodeContext:
    def __init__(self, state: dict, agent: str):
        self.state, self.agent, self.trace_id = state, agent, state["trace_id"]
        self.events: list[dict] = []
        self.delta: dict[str, int] = {}
        counts = state.get("tool_calls") or {}
        self.agent_calls = counts.get(agent, 0)
        self.run_calls = sum(counts.values())

    def emit(self, kind: str, **data) -> dict:
        data.pop("agent", None)          # the agent name is always the node's own
        ev = make_event(self.trace_id, kind, self.agent, **data)
        self.events.append(ev)
        return ev

    async def call(self, tool: str, raw_args: dict) -> dict:
        """Validate with Pydantic first; validation errors are returned as feedback, never raised."""
        if self.agent_calls >= settings.PER_AGENT_TOOL_LIMIT:
            raise BudgetExceeded(f"per-agent tool-call limit ({settings.PER_AGENT_TOOL_LIMIT}) reached for {self.agent}")
        if self.run_calls >= settings.PER_RUN_TOOL_LIMIT:
            raise BudgetExceeded(f"per-run tool-call limit ({settings.PER_RUN_TOOL_LIMIT}) reached")
        self.agent_calls += 1
        self.run_calls += 1
        self.delta[self.agent] = self.delta.get(self.agent, 0) + 1
        model_cls, fn = tools.TOOLS[tool]
        try:
            model = model_cls.model_validate(raw_args)
        except ValidationError as e:
            details = [{"field": ".".join(map(str, x["loc"])), "type": x["type"], "msg": x["msg"], "ctx": x.get("ctx", {})}
                       for x in e.errors()]
            self.emit("tool_error", tool=tool, input=raw_args, error="validation_error", details=details)
            return {"ok": False, "error": "validation_error", "details": details}
        payload = model.model_dump(mode="json", exclude_none=True)
        via = "mcp"
        try:
            if not settings.USE_MCP:
                raise RuntimeError("MCP disabled")
            result = await call_mcp_tool(tool, payload)
        except Exception as e:  # MCP unavailable -> same implementation in-process (logged)
            via = f"direct (mcp unavailable: {type(e).__name__})"
            result = fn(model)
        self.emit("tool_call", tool=tool, input=payload, output=result, via=via)
        return {"ok": True, "result": result}

    def update(self, **fields) -> dict:
        return {**fields, "events": self.events, "tool_calls": self.delta, "steps": 1}

    def overflow(self, exc: Exception, **fields) -> dict:
        self.emit("fallback", reason=str(exc))
        return self.update(fallback_reason=str(exc), **fields)
