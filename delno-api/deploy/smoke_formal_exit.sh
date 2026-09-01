#!/usr/bin/env bash
# E0.14 / E1.11 formal exit smoke — staging or local API.
# Usage: DELNO_API_URL=https://a.47z.ru/delno-api bash smoke_formal_exit.sh
set -euo pipefail

API="${DELNO_API_URL:-http://127.0.0.1:18020}"
ADMIN_EMAIL="${DELNO_ADMIN_EMAIL:-admin@delno.one}"
ADMIN_PASSWORD="${DELNO_ADMIN_PASSWORD:-admin123456}"
OWNER_EMAIL="${DELNO_OWNER_EMAIL:-owner@delno.one}"
OWNER_PASSWORD="${DELNO_OWNER_PASSWORD:-demo123456}"

echo "==> E0.14/E1.11 formal exit smoke → ${API}"

for i in 1 2 3 4 5; do
  curl -sf "${API}/v1/health" >/dev/null && break
  sleep 2
done
curl -sf "${API}/v1/health" >/dev/null || { echo "ERROR: API not ready"; exit 1; }

login() {
  local email="$1" pass="$2"
  curl -sf -X POST "${API}/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${email}\",\"password\":\"${pass}\"}" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
}

echo "==> E0.14: admin login"
ADMIN_TOKEN="$(login "${ADMIN_EMAIL}" "${ADMIN_PASSWORD}")"

echo "==> E0.14: list tenants"
curl -sf -H "Authorization: Bearer ${ADMIN_TOKEN}" "${API}/v1/admin/tenants" | head -c 200 && echo

echo "==> E1.11: public FAQ (published CMS)"
curl -sf "${API}/v1/public/cms/pages/faq" | head -c 300 && echo

echo "==> E0.14: tenant auth for feature flags"
TENANT_TOKEN=""
if TENANT_TOKEN="$(login "${OWNER_EMAIL}" "${OWNER_PASSWORD}" 2>/dev/null)"; then
  echo "    using owner credentials"
else
  TENANT_TOKEN="${ADMIN_TOKEN}"
  echo "    owner login skipped — using platform admin token"
fi
curl -sf -H "Authorization: Bearer ${TENANT_TOKEN}" "${API}/v1/tenant/feature-flags" | head -c 300 && echo

echo "==> E0.14: toggle web_voice flag"
curl -sf -X PATCH "${API}/v1/tenant/feature-flags/web_voice" \
  -H "Authorization: Bearer ${TENANT_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"enabled":true}' | head -c 200 && echo

echo "==> E1.11: site FAQ proxy (optional)"
SITE="${DELNO_SITE_URL:-https://a.47z.ru/delno}"
curl -sf "${SITE}/api/cms/faq" 2>/dev/null | head -c 200 && echo || echo "WARN: site proxy skipped"

echo "==> done: formal exit smoke OK"
