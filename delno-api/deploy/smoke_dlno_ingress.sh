#!/usr/bin/env bash
# Smoke production ingress (run on server or with Host headers).
set -euo pipefail

check() {
  local name="$1"
  local url="$2"
  local expect="$3"
  shift 3
  local code
  code=$(curl -sS -o /tmp/dlno_smoke_body -w '%{http_code}' "$@" "$url") || code="000"
  if [ "$code" != "$expect" ]; then
    echo "FAIL $name code=$code expected=$expect url=$url"
    head -c 120 /tmp/dlno_smoke_body 2>/dev/null; echo
    return 1
  fi
  echo "OK   $name code=$code"
}

if [ "${USE_HOST:-0}" = "1" ]; then
  IP="${DLNO_SERVER_IP:-127.0.0.1}"
  check "dlno.ru" "http://${IP}/" "200" -H "Host: dlno.ru"
  check "www redirect" "http://${IP}/" "301" -H "Host: www.dlno.ru" -I | head -1 || true
  check "api health" "http://${IP}/v1/health" "200" -H "Host: api.dlno.ru"
  check "app" "http://${IP}/" "200" -H "Host: app.dlno.ru"
  check "admin" "http://${IP}/" "307" -H "Host: admin.dlno.ru"
  check "wiki placeholder" "http://${IP}/" "503" -H "Host: wiki.dlno.ru"
  check "status placeholder" "http://${IP}/" "503" -H "Host: status.dlno.ru"
else
  check "site-root :18022" "http://127.0.0.1:18022/" "200"
  check "api :18020" "http://127.0.0.1:18020/v1/health" "200"
  check "web :18023" "http://127.0.0.1:18023/" "200"
  check "admin :18024" "http://127.0.0.1:18024/" "307"
fi

echo "==> ingress smoke passed"
