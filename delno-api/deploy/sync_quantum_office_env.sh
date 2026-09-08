#!/usr/bin/env bash
# Copy shared secrets from Quantum Office runtime into /opt/delno/.env
# (OpenAI from ava-mailer, Telegram from ava-text-bot, DaData from ava-outreach).
set -euo pipefail

DELNO_ENV="${DELNO_ENV:-/opt/delno/.env}"
FORCE="${FORCE:-0}"

MAILER_ENV="${MAILER_ENV:-/opt/ava-mailer/.env}"
TEXTBOT_ENV="${TEXTBOT_ENV:-/opt/ava-text-bot/.env}"
OUTREACH_ENV="${OUTREACH_ENV:-/opt/ava-outreach/.env}"

read_env_value() {
  local file="$1"
  local key="$2"
  [ -f "$file" ] || return 0
  local line
  line="$(grep -E "^${key}=" "$file" | tail -1 || true)"
  [ -n "$line" ] || return 0
  local value="${line#*=}"
  value="${value%\"}"
  value="${value#\"}"
  printf '%s' "$value"
}

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$DELNO_ENV" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$DELNO_ENV"
  else
    printf '\n%s=%s\n' "$key" "$value" >> "$DELNO_ENV"
  fi
}

maybe_set() {
  local key="$1"
  local value="$2"
  [ -n "$value" ] || return 0
  local current
  current="$(read_env_value "$DELNO_ENV" "$key")"
  if [ "$FORCE" = "1" ] || [ -z "$current" ]; then
    set_env_value "$key" "$value"
    echo "  ${key}=synced"
  else
    echo "  ${key}=keep existing"
  fi
}

if [ ! -f "$DELNO_ENV" ]; then
  echo "ERROR: ${DELNO_ENV} not found — run install_isolated_prod.sh first"
  exit 1
fi

echo "==> sync Quantum Office secrets → ${DELNO_ENV}"

OPENAI_KEY="$(read_env_value "$MAILER_ENV" OPENAI_API_KEY)"
OPENAI_MODEL="$(read_env_value "$MAILER_ENV" OPENAI_MODEL)"
TELEGRAM_TOKEN="$(read_env_value "$TEXTBOT_ENV" TELEGRAM_BOT_TOKEN)"
DADATA_KEY="$(read_env_value "$OUTREACH_ENV" DADATA_API_KEY)"
DADATA_SECRET="$(read_env_value "$OUTREACH_ENV" DADATA_SECRET_KEY)"

maybe_set OPENAI_API_KEY "$OPENAI_KEY"
maybe_set OPENAI_MODEL "$OPENAI_MODEL"
maybe_set MODEL_PROVIDER openai
maybe_set DELNO_TTS_VOICE cedar
maybe_set TELEGRAM_BOT_TOKEN "$TELEGRAM_TOKEN"
maybe_set DADATA_API_KEY "$DADATA_KEY"
maybe_set DADATA_SECRET_KEY "$DADATA_SECRET"

chmod 600 "$DELNO_ENV"
echo "==> done"
