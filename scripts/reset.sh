#!/usr/bin/env bash
# One command: wipe Qdrant + mem0, then rebuild the index from data/docs/.
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/reset_stores.py
python -m src.ingest_qdrant
echo "✔ reset complete"
