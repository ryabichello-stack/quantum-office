#!/usr/bin/env bash
# Deploy quantum-text-bot to prod server (/opt/ava-text-bot).
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/opt/ava-text-bot"
SERVICE="ava-text-bot.service"

echo "==> sync to ${DEST}"
mkdir -p "${DEST}"
rsync -a --delete \
  --exclude venv --exclude data --exclude .env \
  "${SRC_DIR}/" "${DEST}/"

if [ ! -d "${DEST}/venv" ]; then
  python3 -m venv "${DEST}/venv"
fi
"${DEST}/venv/bin/pip" install -q -r "${DEST}/requirements.txt"

if [ ! -f "${DEST}/.env" ]; then
  echo "==> creating .env from ava-mailer"
  MAILER_ENV="/opt/ava-mailer/.env"
  OPENAI_KEY="$(grep -E '^OPENAI_API_KEY=' "${MAILER_ENV}" | cut -d= -f2- | tr -d '\"' || true)"
  OPENAI_MODEL="$(grep -E '^OPENAI_MODEL=' "${MAILER_ENV}" | cut -d= -f2- | tr -d '\"' || true)"
  cp "${DEST}/.env.example" "${DEST}/.env"
  sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=${OPENAI_KEY}|" "${DEST}/.env"
  if [ -n "${OPENAI_MODEL}" ]; then
    sed -i "s|^OPENAI_MODEL=.*|OPENAI_MODEL=${OPENAI_MODEL}|" "${DEST}/.env"
  fi
  chmod 600 "${DEST}/.env"
  echo "WARN: set TELEGRAM_BOT_TOKEN in ${DEST}/.env and restart service"
fi

install -m 644 "${SRC_DIR}/ava-text-bot.service" "/etc/systemd/system/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2
curl -sf "http://127.0.0.1:8011/health" | python3 -m json.tool || true
systemctl --no-pager status "${SERVICE}" | head -12
