#!/usr/bin/env bash
# Safe smoke for the single Hermes multiplex pool — does NOT touch Asterisk/telephony.
set -euo pipefail
cd "$(dirname "$0")/.."

export API_SERVER_KEY="${API_SERVER_KEY:-lab-hermes-key-aaaa}"

echo "== lab compose up (single pool) =="
docker compose -f docker-compose.hermes.yml up -d --no-build hermes-pool || \
  docker compose -f docker-compose.hermes.yml up -d hermes-pool

echo "== wait port =="
for i in $(seq 1 60); do
  if curl -sf -o /dev/null -H "Authorization: Bearer ${API_SERVER_KEY}" http://127.0.0.1:18642/v1/models; then
    echo "pool responding on :18642"
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "WARN: pool not healthy yet; dumping logs"
    docker logs --tail 80 delno-hermes-pool || true
  fi
done

echo "== probe pool =="
curl -sS -m 10 -H "Authorization: Bearer ${API_SERVER_KEY}" http://127.0.0.1:18642/v1/models || true
echo

echo "== containers =="
docker ps --filter name=delno-hermes --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "OK lab smoke finished (telephony untouched)"
