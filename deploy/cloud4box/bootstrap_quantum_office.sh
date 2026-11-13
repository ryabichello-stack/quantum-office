#!/usr/bin/env bash
# Bootstrap Quantum Labs office stack on Cloud4Box after QL loss.
# Run as root on <C4B_HOST> from a synced repo checkout.
# Set C4B_HOST from the host inventory (see README.md). Do not commit the address.
set -euo pipefail

: "${C4B_HOST:?set C4B_HOST to <C4B_HOST> — see deploy/cloud4box/README.md}"

ROOT="${ROOT:-/opt/quantum-office}"
REPO="${REPO:-/opt/quantum-office/src}"
COMPOSE_FILE="${REPO}/deploy/cloud4box/docker-compose.quantum-office.yml"

install -d "$ROOT/data/channel-curate" "$ROOT/logs" "$REPO"

if [ ! -f "$ROOT/.env" ]; then
  umask 077
  WH=$(openssl rand -hex 24)
  CT=$(openssl rand -hex 16)
  UIT=$(openssl rand -hex 12)
  cat > "$ROOT/.env" <<EOF
# Quantum Labs office — Cloud4Box recovery $(date -u +%Y-%m-%dT%H:%MZ)
WEBHOOK_TOKEN=${WH}
OFFICE_WEBHOOK_TOKEN=${WH}
CONSOLE_TOKEN=${CT}
OUTREACH_UI_TOKEN=${UIT}
OUTREACH_ENABLED=false

# Fill these to re-enable live integrations (lost with QL):
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHANNEL_BOT_TOKEN=
SECRETARY_OWNER_IDS=963782

MAIL_SMTP_HOST=
MAIL_SMTP_PORT=465
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_FROM_NAME=Quantum Labs

YANDEX_OAUTH_CLIENT_ID=
YANDEX_OAUTH_CLIENT_SECRET=
YANDEX_OAUTH_REDIRECT_URI=
YANDEX_TELEMOST_OAUTH_TOKEN=

MAILRU_CALDAV_URL=https://calendar.mail.ru
MAILRU_CALDAV_USERNAME=
MAILRU_CALDAV_PASSWORD=

BITRIX_WEBHOOK_URL=
DADATA_API_KEY=
DADATA_SECRET_KEY=

TELEMOST_ENABLED=true
TELEMOST_STUB_WHEN_UNAUTH=true
CONFERENCE_STUB_WHEN_UNAUTH=true
JITSI_ENABLED=true
CONFERENCE_DEFAULT_PROVIDER=yandex
EOF
  chmod 600 "$ROOT/.env"
  echo "created $ROOT/.env (fill secrets)"
else
  echo "keep existing $ROOT/.env"
fi

cd "$REPO"
# shellcheck disable=SC1091
set -a; source "$ROOT/.env"; set +a
export WEBHOOK_TOKEN CONSOLE_TOKEN OUTREACH_UI_TOKEN OUTREACH_ENABLED
export OPENAI_API_KEY OPENAI_MODEL TELEGRAM_BOT_TOKEN TELEGRAM_CHANNEL_BOT_TOKEN
export SECRETARY_OWNER_IDS

docker compose -f "$COMPOSE_FILE" --project-directory "$REPO" build
docker compose -f "$COMPOSE_FILE" --project-directory "$REPO" up -d

# nginx snippet
install -d /etc/nginx/snippets
cp "$REPO/deploy/cloud4box/nginx-quantum-office.conf" /etc/nginx/snippets/quantum-office.conf
if ! grep -q 'snippets/quantum-office.conf' /etc/nginx/sites-enabled/delno 2>/dev/null; then
  # try inject into default site
  SITE=$(ls /etc/nginx/sites-enabled/* 2>/dev/null | head -1 || true)
  if [ -n "${SITE:-}" ] && ! grep -q 'snippets/quantum-office.conf' "$SITE"; then
    sed -i '/server_name/a\    include snippets/quantum-office.conf;' "$SITE" || true
  fi
fi
nginx -t && systemctl reload nginx || true

sleep 3
echo '=== health ==='
for p in 8000 8011 8012 8013 8014 8015 8016 8017; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 3 "http://127.0.0.1:${p}/health" || echo fail)
  echo ":$p -> $code"
done

cat > /root/QL_RECOVERY.txt <<EOF
Quantum Labs disaster recovery on Cloud4Box — $(date -u +%Y-%m-%dT%H:%MZ)

Host: ${C4B_HOST}
Stack: /opt/quantum-office
Env:   /opt/quantum-office/.env (mode 600)
Compose: deploy/cloud4box/docker-compose.quantum-office.yml

Public (HTTP):
  http://${C4B_HOST}/_ava_outreach/
  http://${C4B_HOST}/_quantum_console/
  http://${C4B_HOST}/_ava_secretary/
  http://${C4B_HOST}/_ava_knowledge/
  http://${C4B_HOST}/_ava_conference/

Lost with QL (must re-enter in .env):
  OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, SMTP, Yandex OAuth/Telemost,
  Mail.ru CalDAV, Bitrix webhook, DaData, AVA/Asterisk/Mango (voice),
  knowledge vault content beyond git, polyhub (separate).

Still running separately:
  DELNO stack /opt/delno
  3x-ui / xray REALITY :443
  channel-curate may need TELEGRAM_CHANNEL_BOT_TOKEN in .env
EOF
chmod 600 /root/QL_RECOVERY.txt
echo "Wrote /root/QL_RECOVERY.txt"
