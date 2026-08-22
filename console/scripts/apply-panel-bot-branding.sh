#!/usr/bin/env bash
# Apply Quantum Panel branding to @Quantum_panel_bot via Telegram Bot API.
# Profile photo: upload quantum-panel-bot-512.png via @BotFather → /setuserpic (no Bot API).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${1:-$ROOT/static/brand/quantum-panel-bot-512.png}"
LOCKUP="${ROOT}/static/brand/quantum-panel-bot-lockup-512.png"

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

echo "OK: name + description (ru) applied."

if [[ -f "$IMG" && -n "${NOTIFY_CHAT_ID:-}" ]]; then
  curl -fsS -X POST "$API/sendPhoto" \
    -F "chat_id=${NOTIFY_CHAT_ID}" \
    -F "photo=@${IMG}" \
    --form-string "caption=Quantum Panel — аватар (символ, без текста).\n\n@BotFather → /setuserpic → @Quantum_panel_bot → это фото.\n\nИмя «Quantum Panel» Telegram покажет рядом с иконкой." \
    >/dev/null
  if [[ -f "$LOCKUP" ]]; then
    curl -fsS -X POST "$API/sendPhoto" \
      -F "chat_id=${NOTIFY_CHAT_ID}" \
      -F "photo=@${LOCKUP}" \
      --form-string "caption=Полный lockup с типографикой (для превью / документов)." \
      >/dev/null
  fi
  echo "OK: logo sent to chat ${NOTIFY_CHAT_ID}"
elif [[ -f "$IMG" ]]; then
  echo "Tip: NOTIF_CHAT_ID=963782 $0  # send logo + BotFather hint"
  echo "Avatar: @BotFather → /setuserpic → select bot → upload: $IMG"
fi
