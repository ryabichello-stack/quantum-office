#!/usr/bin/env bash
# Run Quantum Office MCP server for Cursor / Claude / Grok (stdio).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}${PYTHONPATH:+:$PYTHONPATH}"

# Defaults point at local prod-style ports on the office host.
export CONSOLE_BASE="${CONSOLE_BASE:-http://127.0.0.1:8013}"
export CAMPAIGN_BASE="${CAMPAIGN_BASE:-http://127.0.0.1:8018}"
export AVA_KNOWLEDGE_BASE="${AVA_KNOWLEDGE_BASE:-http://127.0.0.1:8017}"
export CALENDAR_BASE="${CALENDAR_BASE:-http://127.0.0.1:8014}"
export OUTREACH_BASE="${OUTREACH_BASE:-http://127.0.0.1:8012}"
export CONFERENCE_BASE="${CONFERENCE_BASE:-http://127.0.0.1:8016}"
export FILES_BASE="${FILES_BASE:-http://127.0.0.1:8015}"
export TEXT_BOT_BASE="${TEXT_BOT_BASE:-http://127.0.0.1:8011}"
export MAILER_BASE="${MAILER_BASE:-http://127.0.0.1:8000}"

# Optional: load tokens from a local env file (never commit secrets).
if [ -f "${ROOT}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "${ROOT}/.env"
  set +a
fi

if [ -x "${ROOT}/venv/bin/python" ]; then
  PY="${ROOT}/venv/bin/python"
elif [ -x /opt/quantum-office-mcp/venv/bin/python ]; then
  PY=/opt/quantum-office-mcp/venv/bin/python
else
  PY=python3
fi

exec "$PY" -m quantum_office_mcp
