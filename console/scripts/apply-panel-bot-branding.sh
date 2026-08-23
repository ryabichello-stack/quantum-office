#!/usr/bin/env bash
# Apply Quantum Panel bot branding (name, description, avatar) via Telegram Bot API.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
JPG="${1:-$ROOT/static/brand/quantum-panel-bot-512.jpg}"

if [[ -f "$ROOT/scripts/render-panel-bot-avatar.py" ]]; then
  python3 "$ROOT/scripts/render-panel-bot-avatar.py" 2>/dev/null || true
fi

if [[ -z "${BOT_TOKEN:-}" ]]; then
  if [[ -f /opt/ava-outreach/data/settings.db ]]; then
    BOT_TOKEN=$(sqlite3 /opt/ava-outreach/data/settings.db \
      "SELECT value FROM app_settings WHERE key='OPS_NOTIFY_TELEGRAM_BOT_TOKEN';")
  fi
fi
if [[ -z "${BOT_TOKEN:-}" ]]; then
  echo "Set BOT_TOKEN or configure OPS_NOTIFY_TELEGRAM_BOT_TOKEN in outreach settings.db" >&2
  exit 1
fi

if [[ ! -f "$JPG" ]]; then
  echo "Avatar JPG not found: $JPG" >&2
  exit 1
fi

API="https://api.telegram.org/bot${BOT_TOKEN}"

SHORT_RU='Quantum Panel — операторский центр Quantum Labs. Outreach, телефония, сервисы.'
DESC_RU='Quantum Panel

Операторский центр управления Quantum Labs — один канал для важных событий.

Outreach · ответы и заявки на звонок
Console · статус робота и сервисов
Телефония · звонки и обзвоны

a.47z.ru/_quantum_console'

curl -fsS -X POST "$API/setMyName" --data-urlencode "name=Quantum Panel" >/dev/null
curl -fsS -X POST "$API/setMyShortDescription" \
  --data-urlencode "short_description=${SHORT_RU}" -d "language_code=ru" >/dev/null
curl -fsS -X POST "$API/setMyDescription" \
  --data-urlencode "description=${DESC_RU}" -d "language_code=ru" >/dev/null
curl -fsS -X POST "$API/setMyProfilePhoto" \
  -F 'photo={"type":"static","photo":"attach://myfile"}' \
  -F "myfile=@${JPG};type=image/jpeg" >/dev/null

echo "OK: Quantum Panel branding applied (name, description, avatar)."
