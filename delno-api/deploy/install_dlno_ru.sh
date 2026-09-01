#!/usr/bin/env bash
# Deploy dlno.ru as primary marketing domain (root site, no /delno prefix).
set -euo pipefail

STACK_DIR="${STACK_DIR:-/opt/delno}"
SITE_SRC="${SITE_SRC:-/opt/delno/site-src}"
ROOT_PORT="18022"
NGINX_AVAILABLE="/etc/nginx/sites-available/dlno.ru.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/dlno.ru.conf"

echo "==> DELNO dlno.ru deploy"

mkdir -p "${STACK_DIR}" "${SITE_SRC}"

if [ -d "${SRC_DIR:-}" ]; then
  echo "==> rsync site source from SRC_DIR=${SRC_DIR}"
  rsync -a --delete \
    --exclude node_modules --exclude .next --exclude .sites-runtime \
    "${SRC_DIR}/" "${SITE_SRC}/"
fi

if [ ! -f "${SITE_SRC}/Dockerfile" ]; then
  echo "ERROR: ${SITE_SRC}/Dockerfile missing. Set SRC_DIR to DELNO-site-v23 checkout."
  exit 1
fi

echo "==> build delno-site-root (NEXT_PUBLIC_BASE_PATH empty)"
docker build \
  --build-arg NEXT_PUBLIC_BASE_PATH= \
  -t delno-site-root:latest \
  "${SITE_SRC}"

docker network create delno-internal 2>/dev/null || true

docker rm -f delno-site-root 2>/dev/null || true
ENV_FILE_ARG=()
if [ -f "${STACK_DIR}/.env" ]; then
  ENV_FILE_ARG=(--env-file "${STACK_DIR}/.env")
fi
docker run -d --name delno-site-root --restart unless-stopped \
  "${ENV_FILE_ARG[@]}" \
  --network delno-internal \
  -e DELNO_API_URL="${DELNO_API_URL:-http://api:8020}" \
  -e DELNO_TENANT_SLUG="${DELNO_TENANT_SLUG:-delno-demo}" \
  -p "127.0.0.1:${ROOT_PORT}:3000" \
  delno-site-root:latest

echo "==> nginx dlno.ru"
cp "${DEPLOY_DIR:-$(dirname "$0")}/nginx-dlno.ru.conf" "${NGINX_AVAILABLE}"
ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
nginx -t
systemctl reload nginx

echo "==> certbot (HTTP-01; Cloudflare must proxy to this server)"
if command -v certbot >/dev/null; then
  certbot --nginx -d dlno.ru -d www.dlno.ru -d api.dlno.ru \
    --non-interactive --agree-tos -m office@dlno.ru --redirect || \
    echo "WARN: certbot failed — check Cloudflare DNS points to this server"
fi

echo "==> smoke"
curl -sf "http://127.0.0.1:${ROOT_PORT}/" | head -c 80 && echo
curl -sf "http://127.0.0.1:18020/v1/health" && echo

echo "==> done"
echo "    https://dlno.ru (after DNS + SSL)"
echo "    https://api.dlno.ru/v1/health"
echo "    staging unchanged: https://a.47z.ru/delno/"
