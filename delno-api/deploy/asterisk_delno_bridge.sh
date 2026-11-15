#!/usr/bin/env bash
# Asterisk dialplan hook → DELNO telephony bridge (inbound start/end + live memory).
#
# Dialplan / AGI:
#   AGI delno_route_call.py → bridge start uniqueid callerid did dnid trunk_id
#   On start, args 5–6 are did_candidate + trunk_id (not session/summary).
#   System(... end uniqueid "" "" "${SESSION_ID}" "${SUMMARY}" "${TRANSCRIPT}")
#
# On start, session_id is written to /tmp/delno-call-<uniqueid>.session for hangup.
set -euo pipefail

ACTION="${1:-start}"
UNIQUEID="${2:-}"
FROM_NUM="${3:-}"
DID="${4:-}"
SESSION_ID="${5:-}"
SUMMARY="${6:-}"
TRANSCRIPT="${7:-}"
RECORDING_URL="${8:-}"

API_BASE="${DELNO_API_BASE:-http://127.0.0.1:18020}"
TOKEN="${TELEPHONY_WEBHOOK_TOKEN:-${OFFICE_WEBHOOK_TOKEN:-}}"
STATE_DIR="${DELNO_CALL_STATE_DIR:-/tmp}"

hdr=(-H "Content-Type: application/json")
if [ -n "$TOKEN" ]; then
  hdr+=(-H "X-Telephony-Token: ${TOKEN}")
fi

state_file() {
  echo "${STATE_DIR}/delno-call-${UNIQUEID}.session"
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read())[1:-1])' <<<"${1:-}"
}

if [ "$ACTION" = "start" ]; then
  # Positional reuse: SESSION_ID ← dnid (did candidate), SUMMARY ← trunk_id from AGI.
  payload="$(python3 - "$DID" "$FROM_NUM" "$UNIQUEID" "$SESSION_ID" "$SUMMARY" <<'JSON'
import json,sys
print(json.dumps({
    "did": sys.argv[1],
    "from_number": sys.argv[2],
    "external_id": sys.argv[3],
    "did_candidates": [sys.argv[4]] if sys.argv[4] else [],
    "trunk_id": sys.argv[5],
}))
JSON
  )"
  resp="$(curl -sf "${API_BASE}/v1/telephony/inbound/start" \
    "${hdr[@]}" -d "$payload" || true)"
  if [ -n "$resp" ] && [ -n "$UNIQUEID" ]; then
    sid="$(python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); print((d.get("session") or {}).get("id") or "")' <<<"$resp" || true)"
    if [ -n "$sid" ]; then
      echo "$sid" >"$(state_file)"
    fi
  fi
  echo "$resp"
  exit 0
fi

if [ "$ACTION" = "end" ]; then
  sid="$SESSION_ID"
  if [ -z "$sid" ] && [ -n "$UNIQUEID" ] && [ -f "$(state_file)" ]; then
    sid="$(cat "$(state_file)" 2>/dev/null || true)"
  fi
  if [ -z "$sid" ]; then
    echo '{"ok":false,"error":"session_id_missing"}' >&2
    exit 1
  fi
  sum_esc="$(json_escape "${SUMMARY}")"
  tr_esc="$(json_escape "${TRANSCRIPT}")"
  rec_esc="$(json_escape "${RECORDING_URL}")"
  payload="{\"session_id\":\"${sid}\",\"summary\":\"${sum_esc}\",\"transcript\":\"${tr_esc}\",\"outcome\":\"completed\",\"generate_summary\":true"
  if [ -n "$RECORDING_URL" ]; then
    payload="${payload},\"recording_url\":\"${rec_esc}\""
  fi
  payload="${payload}}"
  curl -sf "${API_BASE}/v1/telephony/calls/end" "${hdr[@]}" -d "$payload" || true
  rm -f "$(state_file)" || true
  exit 0
fi

if [ "$ACTION" = "turn" ]; then
  TEXT="${5:-}"
  sid="$SESSION_ID"
  if [ -z "$sid" ] && [ -n "$UNIQUEID" ] && [ -f "$(state_file)" ]; then
    sid="$(cat "$(state_file)" 2>/dev/null || true)"
  fi
  if [ -z "$sid" ] || [ -z "$TEXT" ]; then
    echo '{"ok":false,"error":"session_or_text_missing"}' >&2
    exit 1
  fi
  text_esc="$(json_escape "${TEXT}")"
  curl -sf "${API_BASE}/v1/telephony/calls/turn" \
    "${hdr[@]}" \
    -d "{\"session_id\":\"${sid}\",\"text\":\"${text_esc}\"}" || true
  exit 0
fi

echo "usage: $0 start|end|turn uniqueid from did [session_id|dnid] [summary|trunk_id|text] [transcript] [recording_url]" >&2
exit 2
