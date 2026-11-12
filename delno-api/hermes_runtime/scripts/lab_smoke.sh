#!/usr/bin/env bash
# Safe dogfood smoke for isolated Hermes lab — does NOT touch Asterisk/telephony/prod API.
# Run on C4B from /opt/delno/lab/hermes_runtime after image build.
set -euo pipefail
cd "$(dirname "$0")/.."

# API_SERVER_KEY must be >=16 chars (hermes adapter guard).
export API_SERVER_KEY="${API_SERVER_KEY:-lab-hermes-key-aaaa}"
export API_SERVER_KEY_B="${API_SERVER_KEY_B:-lab-hermes-key-bbbb}"

echo "== lab compose up =="
docker compose -f docker-compose.hermes.yml up -d --no-build hermes-tenant-a hermes-tenant-b || \
  docker compose -f docker-compose.hermes.yml up -d hermes-tenant-a hermes-tenant-b

echo "== wait ports =="
for i in $(seq 1 60); do
  if curl -sf -o /dev/null -H "Authorization: Bearer ${API_SERVER_KEY}" http://127.0.0.1:18642/health \
    || curl -sf -o /dev/null http://127.0.0.1:18642/v1/models \
    || curl -sf -o /dev/null -H "Authorization: Bearer ${API_SERVER_KEY}" http://127.0.0.1:18642/v1/models; then
    echo "tenant-a responding on :18642"
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "WARN: tenant-a not healthy yet; dumping logs"
    docker logs --tail 80 delno-hermes-tenant-a || true
  fi
done

echo "== probe A =="
curl -sS -m 10 -H "Authorization: Bearer ${API_SERVER_KEY}" http://127.0.0.1:18642/v1/models || true
echo
curl -sS -m 10 -H "Authorization: Bearer ${API_SERVER_KEY}" -H "Content-Type: application/json" \
  -d '{"model":"hermes-agent","messages":[{"role":"user","content":"ping"}]}' \
  http://127.0.0.1:18642/v1/chat/completions || true
echo

echo "== probe B (isolation port) =="
curl -sS -m 10 -H "Authorization: Bearer ${API_SERVER_KEY_B}" http://127.0.0.1:18643/v1/models || true
echo

echo "== containers =="
docker ps --filter name=delno-hermes --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "OK lab smoke finished (telephony untouched)"
