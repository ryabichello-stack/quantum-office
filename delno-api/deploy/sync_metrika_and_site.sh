#!/usr/bin/env bash
# On prod: marketing OAuth → ensure Metrika counter for dlno.ru → rebuild delno-site-root.
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
MAILER_ENV="${MAILER_ENV:-/opt/ava-mailer/.env}"
SITE="${STACK_DIR}/site"

# shellcheck disable=SC1090
source "$MAILER_ENV"
TOKEN="${WEBHOOK_TOKEN:?WEBHOOK_TOKEN missing in mailer env}"
SITE_HOST="${METRIKA_SITE:-dlno.ru}"

marketing_status="$(curl -sf -H "X-Webhook-Token: ${TOKEN}" "http://127.0.0.1:8000/oauth/yandex/marketing/status" || echo '{}')"
if ! echo "$marketing_status" | grep -q '"has_refresh_token": true'; then
  echo "Marketing OAuth token missing. Authorize once:" >&2
  echo "  http://127.0.0.1:8000/oauth/yandex/marketing/manual?token=${TOKEN}" >&2
  exit 1
fi

ensure_json="$(curl -sf "http://127.0.0.1:8000/yandex/metrika/ensure?token=${TOKEN}&site=${SITE_HOST}")"
counter_id="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["counter_id"])' <<<"$ensure_json")"
echo "Metrika counter_id=${counter_id} for ${SITE_HOST}"

ENV_FILE="${STACK_DIR}/.env"
touch "$ENV_FILE"
if grep -q '^YM_COUNTER_ID=' "$ENV_FILE"; then
  sed -i "s/^YM_COUNTER_ID=.*/YM_COUNTER_ID=${counter_id}/" "$ENV_FILE"
else
  echo "YM_COUNTER_ID=${counter_id}" >> "$ENV_FILE"
fi
if grep -q '^NEXT_PUBLIC_YM_COUNTER_ID=' "$ENV_FILE"; then
  sed -i "s/^NEXT_PUBLIC_YM_COUNTER_ID=.*/NEXT_PUBLIC_YM_COUNTER_ID=${counter_id}/" "$ENV_FILE"
else
  echo "NEXT_PUBLIC_YM_COUNTER_ID=${counter_id}" >> "$ENV_FILE"
fi

docker build \
  --build-arg NEXT_PUBLIC_BASE_PATH= \
  --build-arg NEXT_PUBLIC_YM_COUNTER_ID="${counter_id}" \
  -t delno-site-root:latest \
  "$SITE"

docker rm -f delno-site-root 2>/dev/null || true
docker run -d --name delno-site-root --restart unless-stopped \
  --env-file "$ENV_FILE" \
  --network delno-internal \
  -e DELNO_API_URL=http://api:8020 \
  -e DELNO_TENANT_SLUG=delno-demo \
  -e YM_COUNTER_ID="${counter_id}" \
  -e NEXT_PUBLIC_YM_COUNTER_ID="${counter_id}" \
  -p 127.0.0.1:18022:3000 \
  delno-site-root:latest

curl -sf "http://127.0.0.1:18022/v2" | grep -q "mc.yandex.ru/metrika" && echo "Metrika snippet OK on /v2"
