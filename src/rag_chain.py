"""Qdrant retrieval (top-4). Returns passage IDs next to the text so drafts can cite real documents."""
import atexit

from qdrant_client import QdrantClient, models

from . import settings
from .llm import embed

_client = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        if settings.QDRANT_URL:
            _client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
        else:
            settings.QDRANT_LOCAL_PATH.mkdir(parents=True, exist_ok=True)
            _client = QdrantClient(path=str(settings.QDRANT_LOCAL_PATH))
        atexit.register(_client.close)
    return _client


def retrieve(query: str, k: int = settings.TOP_K, doc_type: str | None = None) -> list[dict]:
    client = get_qdrant_client()
    if not client.collection_exists(settings.COLLECTION):
        raise RuntimeError("Qdrant collection missing. Run: python -m src.ingest_qdrant")
    flt = models.Filter(must=[models.FieldCondition(key="doc_type", match=models.MatchValue(value=doc_type))]) if doc_type else None
    vec = embed([query], task="RETRIEVAL_QUERY")[0]
    res = client.query_points(settings.COLLECTION, query=vec, limit=k, query_filter=flt, with_payload=True)
    return [{"id": p.payload["doc_id"], "chunk": p.payload["chunk"], "doc_type": p.payload["doc_type"],
             "score": round(float(p.score), 4), "text": p.payload["text"]} for p in res.points]
