#!/usr/bin/env bash
# Apply Quantum Panel branding to @Quantum_panel_bot via Telegram Bot API.
# Profile photo: upload quantum-panel-bot-512.png via @BotFather → /setuserpic (no Bot API).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IMG="${1:-$ROOT/static/brand/quantum-panel-bot-512.png}"

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

SHORT_RU='Quantum Panel — операторский пульт Quantum Labs. Уведомления: Outreach, звонки, сервисы, алерты центра управления.'
DESC_RU='Quantum Panel — операторский пульт Quantum Labs.

Единый Telegram-канал уведомлений центра управления:
• Outreach — ответы на письма, пауза ящика, заявки «Перезвонить»
• Console — статус сервисов и робота
• Звонки и обзвоны

Настройка: https://a.47z.ru/_quantum_console/
Пульт → «Уведомления Quantum Panel»'

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
    --form-string "caption=Логотип Quantum Panel. Чтобы установить аватар бота: @BotFather → /setuserpic → @Quantum_panel_bot → отправьте это фото." \
    >/dev/null
  echo "OK: logo sent to chat ${NOTIFY_CHAT_ID}"
elif [[ -f "$IMG" ]]; then
  echo "Tip: NOTIF_CHAT_ID=963782 $0  # send logo + BotFather hint"
  echo "Avatar: @BotFather → /setuserpic → select bot → upload: $IMG"
fi
