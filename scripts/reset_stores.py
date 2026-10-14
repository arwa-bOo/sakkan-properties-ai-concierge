"""Wipes the Qdrant collection + the mem0 store (called by scripts/reset.sh)."""
import shutil
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from src import settings  # noqa: E402

if settings.QDRANT_URL:
    from qdrant_client import QdrantClient
    c = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY or None)
    for name in (settings.COLLECTION, "sakkan_memory"):
        if c.collection_exists(name):
            c.delete_collection(name)
    print("Qdrant (remote) collections dropped")
for path in (settings.QDRANT_LOCAL_PATH, settings.MEMORY_DIR):
    shutil.rmtree(path, ignore_errors=True)
    print("removed", path)
