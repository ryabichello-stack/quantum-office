#!/usr/bin/env bash
# Follow-up wave 1 on PROD — silent partners only (excludes unsub + warm).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export TZ=Europe/Moscow
export PARTNER_SEND_ENABLED=true
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/fu1_now_$(date +%Y%m%dT%H%M%S).log"
echo "[$(date '+%F %T %Z')] FU1 starting → $LOG"
setsid bash -c "export TZ=Europe/Moscow PARTNER_SEND_ENABLED=true; exec python3 -u $ROOT/scripts/send_campaign.py --wave fu1 --priority ALL --limit 50" >>"$LOG" 2>&1 < /dev/null &
echo $! > "$LOG_DIR/fu1_now.pid"
echo "[$(date '+%F %T %Z')] pid=$(cat "$LOG_DIR/fu1_now.pid") log=$LOG"
