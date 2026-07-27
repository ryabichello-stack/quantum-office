#!/usr/bin/env bash
# Run Quantum Labs Second Brain MCP server for Cursor (stdio).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"
export AVA_KNOWLEDGE_BASE="${AVA_KNOWLEDGE_BASE:-http://127.0.0.1:8017}"
export BRAIN_MCP_PRINCIPAL="${BRAIN_MCP_PRINCIPAL:-service:cursor-admin}"
export BRAIN_MCP_ADMIN="${BRAIN_MCP_ADMIN:-true}"
export BRAIN_MCP_USER_ID="${BRAIN_MCP_USER_ID:-cursor-mcp}"
export BRAIN_TENANT_ID="${BRAIN_TENANT_ID:-quantum-labs}"

if [ -x /opt/ava-knowledge/venv/bin/python ]; then
  PY=/opt/ava-knowledge/venv/bin/python
elif [ -x "${ROOT}/venv/bin/python" ]; then
  PY="${ROOT}/venv/bin/python"
else
  PY=python3
fi
exec "$PY" -m brain_platform.mcp
