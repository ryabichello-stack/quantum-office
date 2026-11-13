#!/usr/bin/env bash
# Production ingress: dlno.ru + subdomains (nginx, Docker UIs, SSL).
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
STACK_DIR="${STACK_DIR:-/opt/delno}"
REPO_ROOT="${REPO_ROOT:-${STACK_DIR}/src}"
SITE_SRC="${SITE_SRC:-${STACK_DIR}/site}"
WEB_SRC="${WEB_SRC:-${STACK_DIR}/delno-web}"
ADMIN_SRC="${ADMIN_SRC:-${STACK_DIR}/delno-admin}"

ROOT_PORT="${ROOT_PORT:-18022}"
WEB_PORT="${WEB_PORT:-18023}"
ADMIN_PORT="${ADMIN_PORT:-18024}"

NGINX_AVAILABLE="/etc/nginx/sites-available/dlno.ru.conf"
NGINX_ENABLED="/etc/nginx/sites-enabled/dlno.ru.conf"

SSL_DOMAINS=(
  dlno.ru
  www.dlno.ru
  api.dlno.ru
  app.dlno.ru
  admin.dlno.ru
  wiki.dlno.ru
  cdn.dlno.ru
  status.dlno.ru
)

echo "==> DELNO production ingress (dlno.ru + subdomains)"

mkdir -p "${STACK_DIR}/ingress/wiki" "${STACK_DIR}/ingress/status" "${STACK_DIR}/cdn"

echo "==> static placeholders (wiki/status/cdn — not live products)"
cp -a "${DEPLOY_DIR}/static/wiki/." "${STACK_DIR}/ingress/wiki/"
cp -a "${DEPLOY_DIR}/static/status/." "${STACK_DIR}/ingress/status/"
cp -a "${DEPLOY_DIR}/static/cdn/." "${STACK_DIR}/cdn/"

docker network create delno-internal 2>/dev/null || true

ENV_FILE_ARG=()
if [ -f "${STACK_DIR}/.env" ]; then
  ENV_FILE_ARG=(--env-file "${STACK_DIR}/.env")
fi

# --- Marketing site root (dlno.ru) ---
if [ -f "${SITE_SRC}/Dockerfile" ]; then
  echo "==> build delno-site-root :${ROOT_PORT}"
  docker build \
    --build-arg NEXT_PUBLIC_BASE_PATH= \
    -t delno-site-root:latest \
    "${SITE_SRC}"
  docker rm -f delno-site-root 2>/dev/null || true
  docker run -d --name delno-site-root --restart unless-stopped \
    "${ENV_FILE_ARG[@]}" \
    --network delno-internal \
    -e DELNO_API_URL="${DELNO_API_URL:-http://api:8020}" \
    -e DELNO_TENANT_SLUG="${DELNO_TENANT_SLUG:-delno-demo}" \
    -p "127.0.0.1:${ROOT_PORT}:3000" \
    delno-site-root:latest
else
  echo "WARN: ${SITE_SRC}/Dockerfile missing — skip site-root (dlno.ru will 502)"
fi

# --- Tenant cabinet (app.dlno.ru) ---
if [ -f "${WEB_SRC}/Dockerfile" ]; then
  echo "==> build delno-web :${WEB_PORT}"
  docker build \
    --build-arg NEXT_PUBLIC_DELNO_API_URL="${NEXT_PUBLIC_DELNO_API_URL:-https://api.dlno.ru}" \
    -t delno-web:latest \
    "${WEB_SRC}"
  docker rm -f delno-web 2>/dev/null || true
  docker run -d --name delno-web --restart unless-stopped \
    -e NEXT_PUBLIC_DELNO_API_URL="${NEXT_PUBLIC_DELNO_API_URL:-https://api.dlno.ru}" \
    -p "127.0.0.1:${WEB_PORT}:3000" \
    delno-web:latest
else
  echo "WARN: ${WEB_SRC}/Dockerfile missing — skip delno-web"
fi

# --- Platform admin (admin.dlno.ru) ---
if [ -f "${ADMIN_SRC}/Dockerfile" ]; then
  echo "==> build delno-admin :${ADMIN_PORT}"
  docker build \
    --build-arg NEXT_PUBLIC_DELNO_API_URL="${NEXT_PUBLIC_DELNO_API_URL:-https://api.dlno.ru}" \
    -t delno-admin:latest \
    "${ADMIN_SRC}"
  docker rm -f delno-admin 2>/dev/null || true
  docker run -d --name delno-admin --restart unless-stopped \
    -e NEXT_PUBLIC_DELNO_API_URL="${NEXT_PUBLIC_DELNO_API_URL:-https://api.dlno.ru}" \
    -p "127.0.0.1:${ADMIN_PORT}:3000" \
    delno-admin:latest
else
  echo "WARN: ${ADMIN_SRC}/Dockerfile missing — skip delno-admin"
fi

echo "==> nginx dlno.ru vhosts"
cp "${DEPLOY_DIR}/nginx-dlno.ru.conf" "${NGINX_AVAILABLE}"
ln -sf "${NGINX_AVAILABLE}" "${NGINX_ENABLED}"
nginx -t
systemctl reload nginx

echo "==> certbot (requires DNS A/CNAME → this server, not Cloudflare proxy-only)"
if command -v certbot >/dev/null; then
  CERTBOT_ARGS=()
  for d in "${SSL_DOMAINS[@]}"; do
    CERTBOT_ARGS+=(-d "$d")
  done
  if certbot --nginx "${CERTBOT_ARGS[@]}" \
    --non-interactive --agree-tos -m "${CERTBOT_EMAIL:-office@dlno.ru}" \
    --redirect --cert-name dlno.ru; then
    echo "==> enforce www → apex redirect on HTTPS"
    # certbot may merge www with apex; ensure www redirects to non-www
    if ! grep -q 'server_name www.dlno.ru' "${NGINX_AVAILABLE}" || \
       ! grep -A2 'server_name www.dlno.ru' "${NGINX_AVAILABLE}" | grep -q 'return 301'; then
      echo "NOTE: verify www.dlno.ru → 301 https://dlno.ru in ${NGINX_AVAILABLE}"
    fi
  else
    echo "WARN: certbot failed — DNS must point to $(curl -sf ifconfig.me 2>/dev/null || echo SERVER_IP)"
    echo "      Current public DNS may still be Cloudflare; use reg.ru A @ → 5.35.86.62"
  fi
else
  echo "WARN: certbot not installed — apt install certbot python3-certbot-nginx"
fi

echo "==> local smoke (127.0.0.1)"
curl -sf "http://127.0.0.1:${ROOT_PORT}/" | head -c 60 && echo || echo "site-root: FAIL"
curl -sf "http://127.0.0.1:18020/v1/health" && echo || echo "api: FAIL"
curl -sf "http://127.0.0.1:${WEB_PORT}/" | head -c 60 && echo || echo "web: FAIL"
curl -sf "http://127.0.0.1:${ADMIN_PORT}/" | head -c 60 && echo || echo "admin: FAIL"

echo "==> done"
echo "    https://dlno.ru          — marketing (after DNS + SSL)"
echo "    https://api.dlno.ru      — delno-api"
echo "    https://app.dlno.ru      — delno-web"
echo "    https://admin.dlno.ru    — delno-admin"
echo "    https://wiki.dlno.ru     — placeholder 503"
echo "    https://cdn.dlno.ru      — static dir"
echo "    https://status.dlno.ru   — placeholder 503"
echo "    staging unchanged:       https://a.47z.ru/delno/"
