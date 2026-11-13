#!/usr/bin/env bash
set -euo pipefail

# Multiplex pool worker: HERMES_HOME is the worker root (contains profiles/<company>/).
# HERMES_PROFILES_ROOT/workers/<HERMES_WORKER_ID> is the shared volume layout with delno-api.
PROFILES_ROOT="${HERMES_PROFILES_ROOT:-/data/hermes-profiles}"

if [[ -n "${HERMES_WORKER_ID:-}" ]]; then
  export HERMES_HOME="${PROFILES_ROOT}/workers/${HERMES_WORKER_ID}"
elif [[ -n "${HERMES_PROFILE_ID:-}" ]]; then
  # Legacy single-profile bind (pre-multiplex dogfood). Prefer worker root when present.
  LEGACY_FLAT="${PROFILES_ROOT}/${HERMES_PROFILE_ID}"
  WORKER_GUESS="${PROFILES_ROOT}/workers/tenant-a"
  if [[ -d "${PROFILES_ROOT}/workers" ]]; then
    # Prefer an existing workers/* root that already hosts this profile.
    FOUND=""
    for d in "${PROFILES_ROOT}"/workers/*/profiles/"${HERMES_PROFILE_ID}"; do
      if [[ -d "$d" ]]; then
        FOUND="$(dirname "$(dirname "$d")")"
        break
      fi
    done
    export HERMES_HOME="${FOUND:-$WORKER_GUESS}"
  else
    export HERMES_HOME="${LEGACY_FLAT}"
  fi
elif [[ -f /data/hermes/.delno_bound_profile ]]; then
  BOUND="$(tr -d '[:space:]' </data/hermes/.delno_bound_profile || true)"
  if [[ -n "$BOUND" && -d "${PROFILES_ROOT}/workers" ]]; then
    for d in "${PROFILES_ROOT}"/workers/*/profiles/"${BOUND}"; do
      if [[ -d "$d" ]]; then
        export HERMES_HOME="$(dirname "$(dirname "$d")")"
        break
      fi
    done
  fi
fi

export HERMES_HOME="${HERMES_HOME:-/data/hermes}"
mkdir -p "$HERMES_HOME"/{memories,skills,cron,sessions,profiles}

# Seed multiplex root config if empty
if [[ ! -f "$HERMES_HOME/config.yaml" && -f /opt/delno-hermes-templates-root/config.yaml ]]; then
  cp -n /opt/delno-hermes-templates-root/config.yaml "$HERMES_HOME/config.yaml" || true
elif [[ ! -f "$HERMES_HOME/config.yaml" && -f /opt/delno-hermes-templates/../worker_root/config.yaml ]]; then
  cp -n /opt/delno-hermes-templates/../worker_root/config.yaml "$HERMES_HOME/config.yaml" || true
fi
if [[ ! -f "$HERMES_HOME/config.yaml" ]]; then
  cat >"$HERMES_HOME/config.yaml" <<'YAML'
gateway:
  multiplex_profiles: true
  auto_multiplex_migration: true
mcp_servers: {}
YAML
fi

# Ensure root .env carries API_SERVER_KEY for the default listener.
if [[ -n "${API_SERVER_KEY:-}" ]]; then
  if [[ ! -f "$HERMES_HOME/.env" ]] || ! grep -q '^API_SERVER_KEY=' "$HERMES_HOME/.env" 2>/dev/null; then
    echo "API_SERVER_KEY=${API_SERVER_KEY}" >>"$HERMES_HOME/.env"
  fi
fi

# API server key required for /v1/*
: "${API_SERVER_KEY:?API_SERVER_KEY must be set for tenant runtime}"

# Multiplex: never inherit a single-tenant MCP key into the process env —
# company profiles use per-run X-Delno-Run-Id / run tokens via DELNO MCP.
if [[ -n "${DELNO_MCP_KEY:-}" ]]; then
  echo "WARN: DELNO_MCP_KEY set on multiplex worker — prefer empty + run tokens only" >&2
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
