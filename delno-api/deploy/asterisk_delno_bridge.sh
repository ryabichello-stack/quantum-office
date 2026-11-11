#!/usr/bin/env bash
# Asterisk dialplan hook → DELNO telephony bridge (inbound start).
# Usage from dialplan:
#   System(/opt/delno/api/deploy/asterisk_delno_bridge.sh start ${CDR(uniqueid)} ${CALLERID(num)} ${EXTEN})
set -euo pipefail

ACTION="${1:-start}"
UNIQUEID="${2:-}"
FROM_NUM="${3:-}"
DID="${4:-}"

API_BASE="${DELNO_API_BASE:-http://127.0.0.1:18020}"
TOKEN="${TELEPHONY_WEBHOOK_TOKEN:-${OFFICE_WEBHOOK_TOKEN:-}}"

hdr=(-H "Content-Type: application/json")
if [ -n "$TOKEN" ]; then
  hdr+=(-H "X-Telephony-Token: ${TOKEN}")
fi

if [ "$ACTION" = "start" ]; then
  curl -sf "${API_BASE}/v1/telephony/inbound/start" \
    "${hdr[@]}" \
    -d "{\"did\":\"${DID}\",\"from_number\":\"${FROM_NUM}\",\"external_id\":\"${UNIQUEID}\"}" \
    || true
fi
