#!/usr/bin/env bash
# Deploy quantum-outreach to prod (/opt/ava-outreach).
# Safe for telephony: only installs this unit; never touches asterisk/AVA/mango/mailer code.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEST="/opt/ava-outreach"
SERVICE="ava-outreach.service"
MAILER_ENV="/opt/ava-mailer/.env"

echo "==> sync to ${DEST} (preserve .env data venv)"
mkdir -p "${DEST}"
rsync -a --delete \
  --exclude venv --exclude data --exclude .env --exclude '__pycache__' --exclude '*.pyc' \
  "${SRC_DIR}/" "${DEST}/"

if [ ! -d "${DEST}/venv" ]; then
  python3 -m venv "${DEST}/venv"
fi
"${DEST}/venv/bin/pip" install -q -r "${DEST}/requirements.txt"

mkdir -p "${DEST}/data"

if [ ! -f "${DEST}/.env" ]; then
  echo "==> creating .env from example + MAIL_* from ava-mailer"
  cp "${DEST}/.env.example" "${DEST}/.env"
  if [ -f "${MAILER_ENV}" ]; then
    for key in MAIL_SMTP_HOST MAIL_SMTP_PORT MAIL_USERNAME MAIL_PASSWORD; do
      val="$(grep -E "^${key}=" "${MAILER_ENV}" | head -1 | cut -d= -f2- || true)"
      if [ -n "${val}" ]; then
        # Escape sed specials in value minimally
        esc="$(printf '%s' "${val}" | sed -e 's/[\\/&]/\\&/g')"
        sed -i "s|^${key}=.*|${key}=${esc}|" "${DEST}/.env"
      fi
    done
  else
    echo "WARN: ${MAILER_ENV} missing — set MAIL_* manually"
  fi
  if [ -n "${BITRIX_WEBHOOK_URL:-}" ]; then
    esc="$(printf '%s' "${BITRIX_WEBHOOK_URL}" | sed -e 's/[\\/&]/\\&/g')"
    sed -i "s|^BITRIX_WEBHOOK_URL=.*|BITRIX_WEBHOOK_URL=${esc}|" "${DEST}/.env"
  else
    echo "WARN: BITRIX_WEBHOOK_URL not set — sync will wait for webhook in ${DEST}/.env"
  fi
  # Hard safety default
  sed -i 's|^OUTREACH_ENABLED=.*|OUTREACH_ENABLED=false|' "${DEST}/.env"
  chmod 600 "${DEST}/.env"
else
  echo "==> keeping existing ${DEST}/.env"
fi

install -m 644 "${SRC_DIR}/ava-outreach.service" "/etc/systemd/system/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"
systemctl restart "${SERVICE}"
sleep 2
curl -sf "http://127.0.0.1:8012/health" | python3 -m json.tool
TOKEN="$("${DEST}/venv/bin/python" "${DEST}/main.py" ui-token)"
echo "==> UI token ready (see OUTREACH_UI_TOKEN in ${DEST}/.env)"
echo "==> local UI: http://127.0.0.1:8012/ui/  (token required)"
systemctl --no-pager status "${SERVICE}" | head -15

# Optional nginx path if site config exists and snippet not yet applied
NGINX_SITE="/etc/nginx/sites-enabled/47z.ru-a.conf"
SNIPPET_MARK="_ava_outreach"
if [ -f "${NGINX_SITE}" ] && ! grep -q "${SNIPPET_MARK}" "${NGINX_SITE}"; then
  echo "==> adding nginx location /_ava_outreach/ to ${NGINX_SITE}"
  python3 - <<PY
from pathlib import Path
path = Path("${NGINX_SITE}")
text = path.read_text()
snippet = '''
  # Quantum Labs AVA Outreach admin (token-auth in app)
  location /_ava_outreach/ {
    proxy_pass http://127.0.0.1:8012/;
    proxy_http_version 1.1;
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
'''
# Insert before the catch-all "location / {" if present, else append before last closing brace
needle = "  location / {"
if needle in text and "location /_ava_outreach/" not in text:
    text = text.replace(needle, snippet + "\n" + needle, 1)
    path.write_text(text)
    print("nginx snippet inserted")
else:
    print("nginx snippet skipped (already present or no location /)")
PY
  nginx -t && systemctl reload nginx || echo "WARN: nginx reload skipped"
else
  echo "==> nginx outreach location already present or site missing"
fi

echo "==> telephony untouched check"
systemctl is-active asterisk ava-mailer quantum-ava-docker >/dev/null
echo "asterisk=$(systemctl is-active asterisk) ava-mailer=$(systemctl is-active ava-mailer) quantum-ava-docker=$(systemctl is-active quantum-ava-docker)"
echo "public UI (if nginx ok): https://a.47z.ru/_ava_outreach/ui/"
# do not echo token to logs by default — operator can run: python main.py ui-token
: "${TOKEN}"
