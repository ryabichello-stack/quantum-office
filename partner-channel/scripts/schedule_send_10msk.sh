#!/usr/bin/env bash
# Schedule partner-channel blast from rdv@ starting 10:00 Europe/Moscow.
# Isolated from ava-outreach / office@ limits.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export TZ=Europe/Moscow
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/scheduled_send_$(date +%Y%m%d).log"

# Enable real send for this scheduled job only (env file may still say false).
export PARTNER_SEND_ENABLED=true

TARGET_HOUR="${PARTNER_SEND_HOUR:-10}"
TARGET_MIN="${PARTNER_SEND_MINUTE:-0}"

echo "[$(date '+%F %T %Z')] scheduler started; target ${TARGET_HOUR}:$(printf '%02d' "$TARGET_MIN") MSK" | tee -a "$LOG"

while true; do
  now_h=$(date +%H)
  now_m=$(date +%M)
  now_s=$((10#$now_h * 3600 + 10#$now_m * 60 + 10#$(date +%S)))
  tgt_s=$((10#$TARGET_HOUR * 3600 + 10#$TARGET_MIN * 60))
  if (( now_s >= tgt_s )); then
    break
  fi
  sleep 30
done

echo "[$(date '+%F %T %Z')] starting FULL list send (ALL priorities, limit 50, 10–15 min jitter)" | tee -a "$LOG"
# Load secrets from local env without printing them
set -a
# shellcheck disable=SC1091
source <(grep -E '^[A-Z0-9_]+=' "$ROOT/smtp.local.env" | sed 's/\r$//')
set +a
export PARTNER_SEND_ENABLED=true

python3 "$ROOT/scripts/send_campaign.py" --priority ALL --limit 50 >>"$LOG" 2>&1
echo "[$(date '+%F %T %Z')] finished with exit=$?" | tee -a "$LOG"
