#!/usr/bin/env bash
# Immediate partner-channel send on PROD — rdv@ only, no OUTREACH_DAILY_LIMIT.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export TZ=Europe/Moscow
export PARTNER_SEND_ENABLED=true
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/send_now_$(date +%Y%m%dT%H%M%S).log"
echo "[$(date '+%F %T %Z')] send_now starting → $LOG"
# Defaults: ALL, limit 50, random 10–15 min jitter (override via args)
nohup python3 "$ROOT/scripts/send_campaign.py" --priority ALL --limit 50 "$@" >>"$LOG" 2>&1 &
echo $! > "$LOG_DIR/send_now.pid"
echo "[$(date '+%F %T %Z')] pid=$(cat "$LOG_DIR/send_now.pid") log=$LOG"
