#!/usr/bin/env bash
set -euo pipefail

# Ensure legacy corpus exists (export from vault if missing/empty).
CONTENT_DIR="${KNOWLEDGE_CONTENT_DIR:-/app/content}"
VAULT="${BRAIN_VAULT_PATH:-/app/vault/quantum-brain}"
MONOLITH="${CONTENT_DIR}/quantum_labs.md"

if [ ! -s "$MONOLITH" ] && [ -d "$VAULT" ]; then
  echo "knowledge: exporting monolith from vault → $MONOLITH"
  PYTHONPATH=/app python3 - <<PY
from pathlib import Path
from brain_platform.publish.export_monolith import export_monolith
r = export_monolith(vault=Path("${VAULT}"), out_path=Path("${MONOLITH}"))
print(r)
PY
fi

# Best-effort vault ingest into Second Brain SQLite (non-fatal).
if [ "${BRAIN_AUTO_INGEST:-true}" = "true" ]; then
  echo "knowledge: auto-ingest vault"
  PYTHONPATH=/app python3 -m brain_platform ingest --sources vault \
    || echo "knowledge: ingest skipped/failed (non-fatal)"
fi

exec "$@"
