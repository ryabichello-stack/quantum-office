#!/usr/bin/env bash
set -euo pipefail

# Prefer an exclusive profile home when DELNO placement binds this worker.
# HERMES_PROFILES_ROOT/<profile_id> is the shared volume with delno-api.
PROFILES_ROOT="${HERMES_PROFILES_ROOT:-/data/hermes-profiles}"
if [[ -n "${HERMES_PROFILE_ID:-}" ]]; then
  export HERMES_HOME="${PROFILES_ROOT}/${HERMES_PROFILE_ID}"
elif [[ -f /data/hermes/.delno_bound_profile ]]; then
  BOUND="$(tr -d '[:space:]' </data/hermes/.delno_bound_profile || true)"
  if [[ -n "$BOUND" && -d "${PROFILES_ROOT}/${BOUND}" ]]; then
    export HERMES_HOME="${PROFILES_ROOT}/${BOUND}"
  fi
fi

export HERMES_HOME="${HERMES_HOME:-/data/hermes}"
mkdir -p "$HERMES_HOME"/{memories,skills,cron,sessions}

# Seed skeleton if empty home
if [[ ! -f "$HERMES_HOME/config.yaml" && -f /opt/delno-hermes-templates/config.yaml ]]; then
  cp -n /opt/delno-hermes-templates/config.yaml "$HERMES_HOME/config.yaml" || true
  cp -n /opt/delno-hermes-templates/SOUL.md "$HERMES_HOME/SOUL.md" || true
  cp -n /opt/delno-hermes-templates/AGENTS.md "$HERMES_HOME/AGENTS.md" || true
fi

# Refuse to start if a foreign profile marker is present and conflicts.
if [[ -f "$HERMES_HOME/.delno_profile_id" ]]; then
  MARKER="$(tr -d '[:space:]' <"$HERMES_HOME/.delno_profile_id" || true)"
  if [[ -n "${HERMES_PROFILE_ID:-}" && -n "$MARKER" && "$MARKER" != "$HERMES_PROFILE_ID" ]]; then
    echo "ERROR: HERMES_HOME belongs to profile '$MARKER' but worker bound to '${HERMES_PROFILE_ID}'" >&2
    exit 1
  fi
fi

# API server key required for /v1/*
: "${API_SERVER_KEY:?API_SERVER_KEY must be set for tenant runtime}"

# Never inherit another tenant's MCP key by accident — require explicit env when using legacy key.
if [[ -z "${DELNO_MCP_KEY:-}" ]]; then
  echo "WARN: DELNO_MCP_KEY empty — Hermes must use X-Delno-Run-Id / run token for MCP" >&2
fi

cd "$HERMES_HOME"

# Upstream CLI surface varies by pin — try known entrypoints.
# Prefer `gateway run` so API_SERVER_* platforms bind in-process.
if command -v hermes >/dev/null 2>&1; then
  if hermes gateway run --help >/dev/null 2>&1; then
    exec hermes gateway run --accept-hooks
  fi
  if hermes gateway --help >/dev/null 2>&1; then
    exec hermes gateway
  fi
  if hermes api-server --help >/dev/null 2>&1; then
    exec hermes api-server
  fi
  exec hermes
fi

if python -c "import hermes_cli" 2>/dev/null; then
  exec python -m hermes_cli gateway run --accept-hooks
fi

echo "ERROR: hermes CLI not found after install; check pin ${HERMES_AGENT_GIT_REF:-unknown}" >&2
exit 1
