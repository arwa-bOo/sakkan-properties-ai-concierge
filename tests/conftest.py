"""Isolate the test run (temp memory / viewings, separate trace log) BEFORE any src import."""
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="sakkan_tests_"))
os.environ["MEMORY_DIR"] = str(_tmp / "memory")
os.environ["VIEWINGS_FILE"] = str(_tmp / "viewings.json")
os.environ.setdefault("TRACE_LOG", str(ROOT / "outputs" / "trace_logs_eval.jsonl"))
if os.getenv("MOCK_MODE", "").lower() in ("1", "true", "yes", "on"):
    os.environ["QDRANT_LOCAL_PATH"] = str(_tmp / "qdrant")      # self-contained offline run

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _index():
    from src import settings
    from src.ingest_qdrant import ingest
    from src.rag_chain import get_qdrant_client
    if settings.MOCK_MODE or not get_qdrant_client().collection_exists(settings.COLLECTION):
        ingest()
