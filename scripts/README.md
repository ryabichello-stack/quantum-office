# scripts

Cloud Agent / local:
- `cloud-agent-install.sh` — idempotent venvs + local `.env` stubs
- `cloud-agent-start.sh` — start mailer / text-bot / outreach and wait for `/health`

Прод-скрипты установки лежат рядом с сервисами:
- `outreach/scripts/install_prod.sh`
- `text-bot/scripts/install_prod.sh`
