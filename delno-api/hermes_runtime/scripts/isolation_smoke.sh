#!/usr/bin/env bash
# P0 isolation smoke for two Hermes lab containers (A :18642, B :18643).
# Does not touch telephony. Requires compose already up + curl.
set -euo pipefail
A_URL="${HERMES_A_URL:-http://127.0.0.1:18642}"
B_URL="${HERMES_B_URL:-http://127.0.0.1:18643}"
A_KEY="${API_SERVER_KEY:-dev-hermes-key-a}"
B_KEY="${API_SERVER_KEY_B:-dev-hermes-key-b}"

echo "== health A =="
curl -sf -H "Authorization: Bearer $A_KEY" "$A_URL/health" || curl -sf -H "Authorization: Bearer $A_KEY" "$A_URL/v1/health" || true
echo
echo "== health B =="
curl -sf -H "Authorization: Bearer $B_KEY" "$B_URL/health" || curl -sf -H "Authorization: Bearer $B_KEY" "$B_URL/v1/health" || true
echo
echo "== keys must differ =="
if [[ "$A_KEY" == "$B_KEY" ]]; then
  echo "FAIL: A and B API keys identical — isolation broken by config"
  exit 1
fi
echo "OK: distinct API keys"
echo "Manual: confirm A cannot list B sessions; MCP tools with tenant A token never return B KB."
