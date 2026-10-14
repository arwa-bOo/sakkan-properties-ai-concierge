"""mem0 long-term memory with three explicit patterns, consent gating and per-client /forget.

Scoping rule: EVERY memory is stored under user_id = client_id. That single rule guarantees
(a) no data is ever mixed between clients and (b) /forget <client_id> is complete.
  kind="preference"  client preferences          (e.g. "needs proximity to international schools")
  kind="deal"        broker's ongoing deals      (metadata.broker_id = the broker who owns the deal)
  kind="episodic"    short summaries of prior turns
mem0 runs self-hosted: Gemini for extraction/embeddings, embedded Qdrant for vectors. We add with
infer=False so exactly the consented text is stored (deterministic, no extra LLM call).
MOCK_MODE swaps the backend for a local JSON file with the same interface."""
import json
import re
import uuid
from datetime import date

from . import settings
from .observability import make_event

KINDS = ("preference", "deal", "episodic")
CLIENT_RE = re.compile(r"^CLT-\d{3}$")


class _MockBackend:
    def __init__(self):
        settings.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.path = settings.MEMORY_DIR / "mock_memory.json"

    def _load(self): return json.loads(self.path.read_text("utf-8")) if self.path.exists() else []
    def _save(self, rows): self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")

    def add(self, text, user_id, metadata):
        rows = self._load()
        rid = uuid.uuid4().hex[:12]
        rows.append({"id": rid, "user_id": user_id, "memory": text, "metadata": metadata})
        self._save(rows)
        return rid

    def get_all(self, user_id): return [r for r in self._load() if r["user_id"] == user_id]

    def search(self, query, user_id, limit):
        q = set(re.findall(r"\w+", query.lower()))
        rows = self.get_all(user_id)
        rows.sort(key=lambda r: -len(q & set(re.findall(r"\w+", r["memory"].lower()))))
        return rows[:limit]

    def delete(self, mid): self._save([r for r in self._load() if r["id"] != mid])


class _Mem0Backend:
    def __init__(self):
        from mem0 import Memory
        settings.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        key = settings.GEMINI_API_KEY
        self.m = Memory.from_config({
            "llm": {"provider": "gemini", "config": {"model": settings.GEMINI_MODEL, "api_key": key}},
            "embedder": {"provider": "gemini", "config": {"model": f"models/{settings.EMBED_MODEL}",
                                                          "embedding_dims": settings.EMBED_DIM, "api_key": key}},
            "vector_store": {"provider": "qdrant", "config": {
                "collection_name": "sakkan_memory", "path": str(settings.MEMORY_DIR / "qdrant"),
                "embedding_model_dims": settings.EMBED_DIM, "on_disk": True}},
            "history_db_path": str(settings.MEMORY_DIR / "history.db"),
        })

    @staticmethod
    def _rows(res):
        rows = res.get("results", []) if isinstance(res, dict) else res
        return [{"id": r["id"], "user_id": r.get("user_id"), "memory": r["memory"], "metadata": r.get("metadata") or {}} for r in rows]

    def add(self, text, user_id, metadata):
        res = self.m.add(text, user_id=user_id, metadata=metadata, infer=False)
        rows = res.get("results", []) if isinstance(res, dict) else res
        return rows[0]["id"] if rows else "n/a"

    def get_all(self, user_id):
        try:                                                    # mem0 >= 1.x / 2.x API
            return self._rows(self.m.get_all(filters={"user_id": user_id}, top_k=500))
        except TypeError:                                       # mem0 0.1.x API
            return self._rows(self.m.get_all(user_id=user_id, limit=500))

    def search(self, query, user_id, limit):
        try:
            return self._rows(self.m.search(query, filters={"user_id": user_id}, top_k=limit))
        except TypeError:
            return self._rows(self.m.search(query, user_id=user_id, limit=limit))

    def delete(self, mid): self.m.delete(mid)


class ClientMemory:
    def __init__(self):
        self.backend = _MockBackend() if settings.MOCK_MODE else _Mem0Backend()

    # ---- read ----------------------------------------------------------------
    def read(self, client_id: str, query: str, limit: int = 5) -> list[dict]:
        if not CLIENT_RE.match(client_id or ""):
            return []
        found = {r["id"]: r for r in self.backend.search(query, client_id, limit)}
        for r in self.backend.get_all(client_id):          # ongoing deals are always relevant
            if r["metadata"].get("kind") == "deal":
                found[r["id"]] = r
        return [{"id": r["id"], "kind": r["metadata"].get("kind", "episodic"), "text": r["memory"], "client_id": client_id}
                for r in found.values()]

    # ---- write (consent-gated) ----------------------------------------------
    def add(self, client_id: str, text: str, kind: str, consent: bool, trace_id: str = "-", broker_id: str = "broker-1") -> dict:
        """The ONLY write path. Refuses unless consent is exactly True."""
        if consent is not True:
            make_event(trace_id, "memory_consent", "memory", client_id=client_id, granted=False)
            return {"ok": False, "reason": "consent_not_given"}
        if kind not in KINDS or not CLIENT_RE.match(client_id or "") or not text.strip():
            return {"ok": False, "reason": "invalid_memory"}
        mid = self.backend.add(text.strip(), client_id, {"kind": kind, "broker_id": broker_id, "date": date.today().isoformat()})
        make_event(trace_id, "memory_write", "memory", client_id=client_id, memory_kind=kind, memory_id=mid, consent=True)
        return {"ok": True, "id": mid}

    def apply_consent(self, trace_id: str, candidates: list[dict], granted: bool, broker_id: str = "broker-1") -> int:
        """Called by the UI after the broker clicked Yes/No on the consent gate."""
        make_event(trace_id, "memory_consent", "memory", granted=granted, n_items=len(candidates))
        if not granted:
            return 0
        return sum(1 for c in candidates if self.add(c["client_id"], c["text"], c["kind"], True, trace_id, broker_id)["ok"])

    # ---- forget ----------------------------------------------------------------
    def forget(self, client_id: str, trace_id: str = "-") -> int:
        """Deletes every memory of the client; returns only the COUNT (never the content)."""
        if not CLIENT_RE.match(client_id or ""):
            raise ValueError("client_id must look like CLT-001")
        rows = self.backend.get_all(client_id)
        for r in rows:
            self.backend.delete(r["id"])
        make_event(trace_id, "memory_forget", "memory", client_id=client_id, removed=len(rows))
        return len(rows)

    def count(self, client_id: str) -> int:
        return len(self.backend.get_all(client_id))


_instance: ClientMemory | None = None


def get_memory() -> ClientMemory:
    global _instance
    if _instance is None:
        _instance = ClientMemory()
    return _instance


def propose_candidates(state: dict, status: str | None = None) -> list[dict]:
    """Memory writes the system WOULD like to make. Nothing is stored until the broker says Yes."""
    cid, plan = state.get("client_id"), state.get("plan", {})
    if not cid:
        return []
    out = []
    if plan.get("remember_text"):
        out.append({"client_id": cid, "kind": "preference", "text": plan["remember_text"]})
    ids = [l["id"] for l in state.get("listings", [])]
    name, today = state.get("client_name", cid), date.today().isoformat()
    if ids and status in ("approved", "edited"):
        out.append({"client_id": cid, "kind": "deal", "text": f"{today}: shortlisted {', '.join(ids)} for {name}; message approved by broker."})
    out.append({"client_id": cid, "kind": "episodic", "text": f"{today}: broker request '{plan.get('intent')}' for {name}; listings: {', '.join(ids) or 'none'}; message: {status or 'n/a'}."})
    return out
