#!/usr/bin/env bash
# Start office services for Cloud Agent / local smoke. Idempotent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"
LOG_DIR="${TMPDIR:-/tmp}/quantum-office"
mkdir -p "${LOG_DIR}"

start_one() {
  local name="$1"
  local port="$2"
  local dir="$3"
  local pidfile="${LOG_DIR}/${name}.pid"
  local logfile="${LOG_DIR}/${name}.log"

  if curl -sf "http://127.0.0.1:${port}/health" >/dev/null 2>&1; then
    echo "${name}: already healthy on :${port}"
    return 0
  fi

  if [[ -f "${pidfile}" ]]; then
    local old
    old="$(cat "${pidfile}" || true)"
    if [[ -n "${old}" ]] && kill -0 "${old}" 2>/dev/null; then
      kill "${old}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${pidfile}"
  fi

  # Free stale listeners if any.
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi

  (
    cd "${dir}"
    # Propagate Cloud Agent secrets into the process when present.
    # Mailer still loads /opt/ava-mailer/.env; text-bot/outreach use dotenv + env.
    nohup env \
      OPENAI_API_KEY="${OPENAI_API_KEY:-}" \
      TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}" \
      BITRIX_WEBHOOK_URL="${BITRIX_WEBHOOK_URL:-}" \
      .venv/bin/uvicorn main:app --host 127.0.0.1 --port "${port}" \
      >"${logfile}" 2>&1 &
    echo $! >"${pidfile}"
  )
  echo "${name}: started pid=$(cat "${pidfile}") log=${logfile}"
}

start_one "mailer" 8000 "${ROOT}/mailer"
start_one "text-bot" 8011 "${ROOT}/text-bot"
start_one "outreach" 8012 "${ROOT}/outreach"

ready=0
for _ in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health >/dev/null \
    && curl -sf http://127.0.0.1:8011/health >/dev/null \
    && curl -sf http://127.0.0.1:8012/health >/dev/null; then
    ready=1
    break
  fi
  sleep 0.5
done

if [[ "${ready}" != "1" ]]; then
  echo "cloud-agent-start: health checks failed" >&2
  tail -n 40 "${LOG_DIR}"/*.log >&2 || true
  exit 1
fi

echo "cloud-agent-start: ok"
curl -s http://127.0.0.1:8012/health; echo
curl -s http://127.0.0.1:8000/health; echo
curl -s http://127.0.0.1:8011/health; echo
