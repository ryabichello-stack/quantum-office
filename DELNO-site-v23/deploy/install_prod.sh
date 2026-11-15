#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/delno-site"
SERVICE="delno-site.service"
PORT="8019"
NGINX_SITE="/etc/nginx/sites-enabled/47z.ru-a.conf"
SNIPPET_MARK="# DELNO site at /delno/"

echo "==> installing DELNO site to ${APP_DIR}"

mkdir -p "${APP_DIR}"
rsync -a --delete \
  --exclude node_modules \
  --exclude .next \
  --exclude .sites-runtime \
  --exclude .wrangler \
  "${SRC_DIR:-.}/" "${APP_DIR}/"

if [ ! -f "${APP_DIR}/.env.production" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env.production"
  echo "WARN: created ${APP_DIR}/.env.production from example — fill secrets"
fi

echo "==> docker build"
docker build -t delno-site:latest "${APP_DIR}"

echo "==> systemd unit"
cat > "/etc/systemd/system/${SERVICE}" <<EOF
[Unit]
Description=DELNO marketing site (Next.js)
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
Restart=always
RestartSec=5
ExecStartPre=-/usr/bin/docker rm -f delno-site
ExecStart=/usr/bin/docker run --name delno-site \\
  --env-file ${APP_DIR}/.env.production \\
  -p 127.0.0.1:${PORT}:3000 \\
  delno-site:latest
ExecStop=/usr/bin/docker stop delno-site

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE}"

if [ -f "${NGINX_SITE}" ] && ! grep -q "${SNIPPET_MARK}" "${NGINX_SITE}"; then
  echo "==> nginx location /delno/"
  python3 - <<'PY'
from pathlib import Path
path = Path("/etc/nginx/sites-enabled/47z.ru-a.conf")
text = path.read_text()
mark = "# DELNO site at /delno/"
block = '''
  ''' + mark + '''
  location /delno/ {
    rewrite ^/delno(/.*)$ $1 break;
    proxy_pass http://127.0.0.1:8019;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /delno;
    proxy_redirect ~^/(.*)$ /delno/$1;
    proxy_read_timeout 120s;
  }
  location = /delno {
    return 308 /delno/;
  }

'''
needle = "  location / {"
if mark not in text and needle in text:
    text = text.replace(needle, block + needle, 1)
    path.write_text(text)
    print("nginx snippet inserted")
else:
    print("nginx snippet skipped")
PY
  nginx -t && systemctl reload nginx
fi

echo "==> done: https://a.47z.ru/delno/"
