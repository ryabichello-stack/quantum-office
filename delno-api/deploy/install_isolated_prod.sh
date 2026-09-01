#!/usr/bin/env bash
# Install isolated DELNO stack under /opt/delno (site + api + postgres).
set -euo pipefail

DELNO_ROOT="/opt/delno"
SERVICE="delno-stack.service"
NGINX_SITE="/etc/nginx/sites-enabled/47z.ru-a.conf"
SNIPPET_MARK="# DELNO site at /delno/"

SITE_SRC="${SITE_SRC:-}"
API_SRC="${API_SRC:-}"

if [[ -z "${SITE_SRC}" || -z "${API_SRC}" ]]; then
  echo "Usage: SITE_SRC=/path/to/DELNO-site-v23 API_SRC=/path/to/delno-api $0"
  exit 1
fi

echo "==> DELNO isolated install → ${DELNO_ROOT}"
mkdir -p "${DELNO_ROOT}/site" "${DELNO_ROOT}/api" "${DELNO_ROOT}/data"

rsync -a --delete \
  --exclude node_modules --exclude .next --exclude .sites-runtime --exclude .wrangler \
  "${SITE_SRC}/" "${DELNO_ROOT}/site/"
rsync -a --delete \
  --exclude .venv --exclude __pycache__ \
  "${API_SRC}/" "${DELNO_ROOT}/api/"

cp "${API_SRC}/deploy/docker-compose.stack.yml" "${DELNO_ROOT}/docker-compose.yml"

if [[ ! -f "${DELNO_ROOT}/.env" ]]; then
  DELNO_PG_PASSWORD="$(openssl rand -hex 16)"
  cat > "${DELNO_ROOT}/.env" <<EOF
# DELNO isolated secrets — do not share with ava-* / polyhub
DELNO_PG_USER=delno
DELNO_PG_PASSWORD=${DELNO_PG_PASSWORD}
DELNO_PG_DB=delno

DEFAULT_TENANT_SLUG=delno-demo

# Public API URL for site (internal docker DNS — service name `api`)
DELNO_API_URL=http://api:8020
DELNO_TENANT_SLUG=delno-demo

# Optional adapters to Quantum Office (leave empty for full isolation)
KNOWLEDGE_BASE_URL=
MESSENGER_BASE_URL=

# Lead notifications (fill manually)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OPENAI_API_KEY=
EOF
  chmod 600 "${DELNO_ROOT}/.env"
  echo "==> created ${DELNO_ROOT}/.env — fill TELEGRAM_* and OPENAI_*"
fi

# stop legacy standalone delno-site systemd (old /opt/delno-site layout)
systemctl disable --now delno-site.service 2>/dev/null || true
# Remove only the old non-compose container (project name delno uses compose labels)
if docker inspect delno-site >/dev/null 2>&1; then
  if ! docker inspect delno-site --format '{{ index .Config.Labels "com.docker.compose.project" }}' 2>/dev/null | grep -q delno; then
    docker rm -f delno-site 2>/dev/null || true
  fi
fi

cd "${DELNO_ROOT}"
docker compose build
docker compose up -d

cat > "/etc/systemd/system/${SERVICE}" <<EOF
[Unit]
Description=DELNO isolated stack (site + api + postgres)
After=docker.service network-online.target
Requires=docker.service
# Isolated: no dependency on ava-* or polyhub

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${DELNO_ROOT}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=600

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"

if [[ -f "${NGINX_SITE}" ]] && ! grep -q "${SNIPPET_MARK}" "${NGINX_SITE}"; then
  python3 - <<'PY'
from pathlib import Path
snippet_path = Path("/opt/delno/api/deploy/nginx-delno.conf.snippet")
nginx_path = Path("/etc/nginx/sites-enabled/47z.ru-a.conf")
block = snippet_path.read_text()
text = nginx_path.read_text()
needle = "  location / {"
mark = "# DELNO site at /delno/"
if mark not in text and needle in text:
    nginx_path.write_text(text.replace(needle, block + needle, 1))
    print("nginx: DELNO snippet inserted")
else:
    print("nginx: skipped (update ports to 18019/18020 manually if snippet exists)")
PY
  nginx -t && systemctl reload nginx
else
  echo "==> nginx: update proxy_pass to 127.0.0.1:18019 and :18020 if migrating from 8019"
fi

echo "==> DELNO stack"
echo "    site: https://a.47z.ru/delno/"
echo "    api:  https://a.47z.ru/delno-api/v1/health"
docker compose ps
