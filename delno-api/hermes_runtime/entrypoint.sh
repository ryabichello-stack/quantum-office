#!/usr/bin/env bash
set -euo pipefail

export HERMES_HOME="${HERMES_HOME:-/data/hermes}"
mkdir -p "$HERMES_HOME"/{memories,skills,cron,sessions}

# Seed skeleton if empty home
if [[ ! -f "$HERMES_HOME/config.yaml" && -f /opt/delno-hermes-templates/config.yaml ]]; then
  cp -n /opt/delno-hermes-templates/config.yaml "$HERMES_HOME/config.yaml" || true
  cp -n /opt/delno-hermes-templates/SOUL.md "$HERMES_HOME/SOUL.md" || true
  cp -n /opt/delno-hermes-templates/AGENTS.md "$HERMES_HOME/AGENTS.md" || true
fi

# API server key required for /v1/*
: "${API_SERVER_KEY:?API_SERVER_KEY must be set for tenant runtime}"

cd "$HERMES_HOME"

# Upstream CLI surface varies by pin — try known entrypoints.
if command -v hermes >/dev/null 2>&1; then
  if hermes gateway --help >/dev/null 2>&1; then
    exec hermes gateway
  fi
  if hermes api-server --help >/dev/null 2>&1; then
    exec hermes api-server
  fi
  exec hermes
fi

if python -c "import hermes_cli" 2>/dev/null; then
  exec python -m hermes_cli gateway
fi

echo "ERROR: hermes CLI not found after install; check pin ${HERMES_AGENT_GIT_REF:-unknown}" >&2
exit 1
