"""trace_id + structlog JSON lines (outputs/trace_logs.jsonl).
Every agent transition, tool call, retrieval, memory op and HiL decision goes through make_event()."""
import json
import re
import uuid

import structlog

from . import settings

_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        settings.TRACE_LOG.parent.mkdir(parents=True, exist_ok=True)
        fh = open(settings.TRACE_LOG, "a", buffering=1, encoding="utf-8")
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="iso", utc=True),
                structlog.processors.JSONRenderer(
                    serializer=lambda obj, **kw: json.dumps(obj, default=str, ensure_ascii=False)),
            ],
            logger_factory=structlog.WriteLoggerFactory(file=fh),
            cache_logger_on_first_use=True,
        )
        _logger = structlog.get_logger("sakkan")
    return _logger


def new_trace_id() -> str:
    return "tr_" + uuid.uuid4().hex[:12]


def make_event(trace_id: str, kind: str, agent: str, **data) -> dict:
    """Log one structured event and return it (the UI renders the returned dict as a cl.Step)."""
    _get_logger().info(kind, trace_id=trace_id, agent=agent, **data)
    return {"trace_id": trace_id, "kind": kind, "agent": agent, **data}


def redact(text: str, allow_client: str | None = None) -> str:
    """Privacy: never leak another client's ID in an error shown to the broker."""
    return re.sub(r"CLT-\d{3}", lambda m: m.group(0) if m.group(0) == allow_client else "[other-client]", str(text))
