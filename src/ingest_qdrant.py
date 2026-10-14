"""Chunk -> embed (Gemini) -> upsert into the `sakkan_properties` Qdrant collection.
Usage: python -m src.ingest_qdrant"""
import time
import uuid

from qdrant_client import models

from . import settings
from .corpus import parse_doc
from .llm import embed
from .rag_chain import get_qdrant_client


def chunk_text(text: str, max_chars: int = 1200) -> list[str]:
    """Docs are short: one chunk each. Longer docs are split on blank lines."""
    if len(text) <= max_chars:
        return [text]
    chunks, cur = [], ""
    for para in text.split("\n\n"):
        if cur and len(cur) + len(para) > max_chars:
            chunks.append(cur.strip()); cur = ""
        cur += para + "\n\n"
    return chunks + ([cur.strip()] if cur.strip() else [])


def ingest() -> int:
    t0 = time.time()
    client = get_qdrant_client()
    if client.collection_exists(settings.COLLECTION):
        client.delete_collection(settings.COLLECTION)
    client.create_collection(settings.COLLECTION, vectors_config=models.VectorParams(
        size=settings.EMBED_DIM, distance=models.Distance.COSINE))
    items = []
    for path in sorted(settings.DOCS_DIR.glob("*.txt")):
        d = parse_doc(path)
        for i, ch in enumerate(chunk_text(d["_text"])):
            items.append({"doc_id": d["ID"], "doc_type": d["DocType"], "chunk": i, "text": ch})
    vectors = embed([x["text"] for x in items])
    client.upsert(settings.COLLECTION, points=[
        models.PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{x["doc_id"]}#{x["chunk"]}')), vector=v, payload=x)
        for x, v in zip(items, vectors)])
    print(f"Ingested {len(items)} chunks from {len(list(settings.DOCS_DIR.glob('*.txt')))} docs "
          f"into '{settings.COLLECTION}' in {time.time() - t0:.1f}s (mock={settings.MOCK_MODE})")
    return len(items)


if __name__ == "__main__":
    ingest()
