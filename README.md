# quantum-office

Quantum Labs office stack + **DELNO** SaaS (не Polyhub trading).

**Prod DELNO:** Cloud4Box `161.104.89.123` · https://dlno.ru · https://app.dlno.ru · https://api.dlno.ru  

**Restore from git (no secrets):** [`docs/DELNO_RESTORE.md`](docs/DELNO_RESTORE.md) · `bash delno-api/deploy/restore_cloud4box.sh`

## DELNO (`/opt/delno`)

| Компонент | Папка |
|-----------|-------|
| API + MCP + alembic | `delno-api/` |
| Кабинет Hermes | `delno-web/` |
| Admin | `delno-admin/` |
| Marketing | `DELNO-site-v23/` |
| Office brokers | `delno-office/` |
| Compose / nginx / restore | `delno-api/deploy/` |
| DNS | `docs/DLNO_DOMAINS.md` |
| Env template | `delno-api/.env.example` → only `/opt/delno/.env` on server |

## Quantum Office brokers

| Сервис | Папка | Порт |
|--------|-------|------|
| Outreach | `outreach/` | 8012 |
| Mailer | `mailer/` | 8000 |
| Text-bot | `text-bot/` | 8011 |
| Console | `console/` | 8013 |
| Knowledge | `knowledge/` | 8017 |
| Calendar / conference / files | `calendar/` `conference/` `files/` | 8014–8016 |

Журнал: [`CHANGELOG.md`](CHANGELOG.md) · git: [`CONTRIBUTING.md`](CONTRIBUTING.md) · агент: [`AGENTS.md`](AGENTS.md)

**Секреты в git не коммитить** — только `.env` на сервере (mode 600).
