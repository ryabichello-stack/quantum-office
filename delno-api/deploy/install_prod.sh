#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/delno-api"
SERVICE="delno-api.service"
PORT="8020"
NGINX_SITE="/etc/nginx/sites-enabled/47z.ru-a.conf"
SNIPPET_MARK="# DELNO API at /delno-api/"

echo "==> install delno-api to ${APP_DIR}"
mkdir -p "${APP_DIR}"
rsync -a --delete --exclude .venv --exclude __pycache__ "${SRC_DIR:-.}/" "${APP_DIR}/"

if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
  echo "WARN: edit ${APP_DIR}/.env"
fi

cd "${APP_DIR}"
docker compose build
docker compose up -d

cat > "/etc/systemd/system/${SERVICE}" <<EOF
[Unit]
Description=DELNO Platform API
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${APP_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"

if [ -f "${NGINX_SITE}" ] && ! grep -q "${SNIPPET_MARK}" "${NGINX_SITE}"; then
  python3 - <<'PY'
from pathlib import Path
path = Path("/etc/nginx/sites-enabled/47z.ru-a.conf")
text = path.read_text()
mark = "# DELNO API at /delno-api/"
block = '''
  ''' + mark + '''
  location /delno-api/ {
    rewrite ^/delno-api(/.*)$ $1 break;
    proxy_pass http://127.0.0.1:8020;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Tenant-Slug delno-demo;
    proxy_read_timeout 120s;
  }

'''
needle = "  # DELNO site at /delno/"
if mark not in text and needle in text:
    text = text.replace(needle, block + needle, 1)
    path.write_text(text)
    print("nginx snippet inserted")
PY
  nginx -t && systemctl reload nginx
fi

echo "==> https://a.47z.ru/delno-api/v1/health"
