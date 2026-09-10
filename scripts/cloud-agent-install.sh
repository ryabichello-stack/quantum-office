#!/usr/bin/env bash
# Idempotent Cloud Agent / local bootstrap for quantum-office services.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # shellcheck disable=SC1091
  source "${HOME}/.local/bin/env"
fi

ensure_venv() {
  local dir="$1"
  local req="$2"
  if [[ ! -x "${dir}/.venv/bin/python" ]]; then
    uv venv "${dir}/.venv"
  fi
  uv pip install -r "${req}" --python "${dir}/.venv/bin/python"
}

ensure_venv "${ROOT}/outreach" "${ROOT}/outreach/requirements.txt"
ensure_venv "${ROOT}/text-bot" "${ROOT}/text-bot/requirements.txt"
ensure_venv "${ROOT}/mailer" "${ROOT}/mailer/requirements.txt"

mkdir -p \
  "${ROOT}/outreach/data" \
  "${ROOT}/text-bot/data" \
  "${ROOT}/.dev/ava-config"

if [[ ! -f "${ROOT}/.dev/ava-config/ai-agent.local.yaml" ]]; then
  cat > "${ROOT}/.dev/ava-config/ai-agent.local.yaml" <<'YAML'
contexts:
  default:
    greeting: "Здравствуйте! Я ИИ-секретарь Quantum Labs. Чем могу помочь?"
    prompt: |
      Ты ИИ-секретарь Quantum Labs. Отвечай кратко и по делу.
YAML
fi

# Mailer hardcodes /opt/ava-mailer/.env — keep a writable stub for local/cloud boots.
if command -v sudo >/dev/null 2>&1; then
  sudo mkdir -p /opt/ava-mailer
  sudo chown -R "$(id -u):$(id -g)" /opt/ava-mailer || true
else
  mkdir -p /opt/ava-mailer || true
fi
touch /opt/ava-mailer/webhook.log

if [[ ! -f /opt/ava-mailer/.env ]]; then
  cat > /opt/ava-mailer/.env <<EOF
WEBHOOK_TOKEN=${WEBHOOK_TOKEN:-dev-webhook-token}
MAIL_SMTP_HOST=${MAIL_SMTP_HOST:-smtp.mail.ru}
MAIL_SMTP_PORT=${MAIL_SMTP_PORT:-465}
MAIL_USERNAME=${MAIL_USERNAME:-office@quantumlabs.ru}
MAIL_PASSWORD=${MAIL_PASSWORD:-}
MAIL_TO_DEFAULT=${MAIL_TO_DEFAULT:-office@quantumlabs.ru}
OPENAI_API_KEY=${OPENAI_API_KEY:-sk-dev-placeholder-not-real}
TELEMOST_ENABLED=false
EOF
  chmod 600 /opt/ava-mailer/.env
fi

if [[ ! -f "${ROOT}/outreach/.env" ]]; then
  cat > "${ROOT}/outreach/.env" <<EOF
BITRIX_PORTAL_URL=${BITRIX_PORTAL_URL:-https://b24-m5614z.bitrix24.ru/}
BITRIX_WEBHOOK_URL=${BITRIX_WEBHOOK_URL:-}
MAIL_SMTP_HOST=${MAIL_SMTP_HOST:-smtp.mail.ru}
MAIL_SMTP_PORT=${MAIL_SMTP_PORT:-465}
MAIL_USERNAME=${MAIL_USERNAME:-office@quantumlabs.ru}
MAIL_PASSWORD=${MAIL_PASSWORD:-}
MAIL_FROM_NAME=Quantum Labs
MAIL_REPLY_TO=office@quantumlabs.ru
OUTREACH_ENABLED=false
OUTREACH_DAILY_LIMIT=15
DATA_DIR=${ROOT}/outreach/data
API_HOST=127.0.0.1
API_PORT=8012
OUTREACH_UI_TOKEN=${OUTREACH_UI_TOKEN:-dev-local-token-quantum}
TRACKING_HMAC_SECRET=${TRACKING_HMAC_SECRET:-devhmacsecret0123456789abcdef}
WARMUP_ENABLED=false
SEQUENCES_ENABLED=true
SCHEDULE_ENABLED=false
REPLY_WATCH_ENABLED=false
OPEN_TRACKING_ENABLED=false
EOF
  chmod 600 "${ROOT}/outreach/.env"
elif [[ -n "${BITRIX_WEBHOOK_URL:-}" ]]; then
  # Refresh webhook from Cloud Agent secrets when present (URLs contain '/').
  ROOT="${ROOT}" BITRIX_WEBHOOK_URL="${BITRIX_WEBHOOK_URL}" python3 - <<'PY'
import os
from pathlib import Path
path = Path(os.environ["ROOT"]) / "outreach" / ".env"
url = os.environ["BITRIX_WEBHOOK_URL"]
text = path.read_text(encoding="utf-8") if path.exists() else ""
lines = text.splitlines()
out, found = [], False
for line in lines:
    if line.startswith("BITRIX_WEBHOOK_URL="):
        out.append(f"BITRIX_WEBHOOK_URL={url}")
        found = True
    else:
        out.append(line)
if not found:
    out.append(f"BITRIX_WEBHOOK_URL={url}")
path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
fi

if [[ ! -f "${ROOT}/text-bot/.env" ]]; then
  cat > "${ROOT}/text-bot/.env" <<EOF
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
OPENAI_MODEL=${OPENAI_MODEL:-gpt-4.1-mini}
AVA_MAILER_BASE=http://127.0.0.1:8000
AVA_CONFIG_PATH=${ROOT}/.dev/ava-config/ai-agent.local.yaml
DATA_DIR=${ROOT}/text-bot/data
TELEGRAM_POLL_INTERVAL_SECONDS=1
EOF
  chmod 600 "${ROOT}/text-bot/.env"
fi

echo "cloud-agent-install: ok"
