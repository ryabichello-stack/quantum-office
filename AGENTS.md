# Quantum Labs Office — Agent Onboarding

**Это репозиторий office-сервисов Quantum Labs**, не Polyhub trading.

## Что здесь

- `outreach/` — Bitrix outreach (FastAPI, `:8012`)
- `mailer/` — post-call письма, календарь, Телемост (`:8000`)
- `text-bot/` — Telegram-бот (`:8011`)
- `delno-api/` — DELNO platform API (multi-tenant SaaS)
- `docs/` — карта прода и состояние

## DELNO (commercial SaaS)

**Мастер-план (canonical):** [`docs/DELNO_MASTER_PLAN.md`](docs/DELNO_MASTER_PLAN.md)

Staging: https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/ · prod path `/opt/delno/`

**Marketing prod:** https://dlno.ru/ (`delno-site-root` :18022) · **API prod:** https://api.dlno.ru/

**Deploy rule:** любой деплoy site/api/knowledge для DELNO — **сразу на оба фронта**: staging `a.47z.ru/delno` **и** prod `dlno.ru`. Скрипт: `delno-api/deploy/deploy_staging_refresh.sh`.

Second Brain (KB foundation): `/opt/ava-knowledge/brain_platform/` → port as `delno-knowledge`

## Прод (справочно)

- SSH: `ssh root@5.35.86.62`
- Сайт: https://a.47z.ru
- UI: https://a.47z.ru/_ava_outreach/ui/

| Путь | Сервис |
|------|--------|
| `/opt/ava-outreach` | `ava-outreach.service` |
| `/opt/ava-mailer` | `ava-mailer.service` |
| `/opt/ava-text-bot` | `ava-text-bot.service` |
| `/opt/polyhub/src` | **НЕ ТРОГАТЬ** (trading) |
| `/root/ava` | Asterisk AVA voice — **не ломать** |

Секреты: `/opt/ava-outreach/.env`, `/opt/ava-mailer/.env`, `/opt/ava-text-bot/.env`.

## Не ломать

Asterisk, AVA docker, Mango, VPN, `/opt/polyhub`.

## Проверки на сервере

```bash
systemctl status ava-outreach ava-mailer ava-text-bot
curl -sf http://127.0.0.1:8012/health
curl -sf http://127.0.0.1:8000/health
curl -sf http://127.0.0.1:8011/health
```

Снаружи: `curl -sf https://a.47z.ru/_ava_outreach/health`

## Cursor Cloud specific instructions

Local Cloud Agent dev does not use production secrets. Postgres 16 listens on `127.0.0.1:5433` (`delno` / `delno` / database `delno`), matching `delno-api` `DATABASE_URL`. Python packages live in `/opt/quantum-office/venv`. `policy-rc.d` blocks `service postgresql`; start the cluster with `pg_ctlcluster`.

Boot services (tmux, idempotent):

| Service | Port | Notes |
|---------|------|--------|
| delno-knowledge | 18021 | SQLite brain at `/opt/quantum-office/data/knowledge` |
| delno-api | 18020 | `MODEL_PROVIDER=stub` so Operator does not call OpenAI |
| delno-web | 3020 | Cabinet UI. Demo login `owner@dlno.ru` / `demo123456` (seeded on API startup) |
| delno-admin | 3010 | `/` redirects to `/login` |
| outreach | 8012 | `OUTREACH_ENABLED=false`. UI token `dev-local-token` |
| mailer | 8000 | Health only; SMTP and Yandex are unset |
| text-bot | 8011 | Degraded until `TELEGRAM_BOT_TOKEN` is set. Prompt stub: `/opt/quantum-office/text-bot-config.yaml` |

```bash
curl -sf http://127.0.0.1:18020/v1/health
curl -sf http://127.0.0.1:18021/health
cd delno-api && PYTHONPATH=. /opt/quantum-office/venv/bin/pytest tests -q
cd delno-knowledge && PYTHONPATH=. /opt/quantum-office/venv/bin/pytest brain_platform/tests/test_security_contracts.py brain_platform/tests/test_tenant_isolation_and_acl.py brain_platform/tests/test_api_acl_smoke.py brain_platform/tests/test_demo_seed.py brain_platform/tests/test_brain_integration.py -q
```

`tests/test_tenant_legal.py::test_update_tenant_legal_endpoint` fails with current httpx (MagicMock used as a header). The rest of `delno-api` tests pass. Do not point these processes at production hosts.
