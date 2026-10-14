"""Central configuration. Everything comes from the environment / .env (never commit .env)."""
import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
os.environ.setdefault("MEM0_TELEMETRY", "False")     # no analytics calls from mem0


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --- modes -------------------------------------------------------------------
MOCK_MODE = _flag("MOCK_MODE")          # deterministic stubs instead of Gemini (offline demo)
USE_MCP = _flag("USE_MCP", True)        # call tools through the MCP stdio server

# --- Gemini --------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
EMBED_MODEL = os.getenv("EMBED_MODEL", "gemini-embedding-001")
EMBED_DIM = 768

# --- Qdrant (Cloud if QDRANT_URL is set, otherwise embedded local mode: no Docker needed) ---
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
QDRANT_LOCAL_PATH = Path(os.getenv("QDRANT_LOCAL_PATH", ROOT / ".qdrant_local"))
COLLECTION = "sakkan_properties"
TOP_K = 4

# --- paths ---------------------------------------------------------------------
DOCS_DIR = ROOT / "data" / "docs"
OUTPUTS = ROOT / "outputs"
TRACE_LOG = Path(os.getenv("TRACE_LOG", OUTPUTS / "trace_logs.jsonl"))
VIEWINGS_FILE = Path(os.getenv("VIEWINGS_FILE", OUTPUTS / "viewings.json"))
MEMORY_DIR = Path(os.getenv("MEMORY_DIR", ROOT / ".memory"))
MCP_SERVER = ROOT / "mcp" / "mcp_tool_server.py"

# --- guardrails ----------------------------------------------------------------
MAX_STEPS = int(os.getenv("MAX_STEPS", 12))
PER_AGENT_TOOL_LIMIT = int(os.getenv("PER_AGENT_TOOL_LIMIT", 4))
PER_RUN_TOOL_LIMIT = int(os.getenv("PER_RUN_TOOL_LIMIT", 10))


def load_rai() -> dict:
    with open(ROOT / "config" / "RAI_Config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
