# DELNO — restore from GitHub (без секретов)

**Цель:** из git всегда можно поднять полный стек на Cloud4Box (`161.104.89.123`).  
**Секреты в git не хранятся** — только `/opt/delno/.env` (mode 600) и бэкапы вне репозитория.

---

## Что в git (SoT)

| Git path | Назначение | Прод path |
|----------|------------|-----------|
| `delno-api/` | API + alembic + MCP | `/opt/delno/api` |
| `delno-web/` | кабинет Hermes | `/opt/delno/web` |
| `delno-admin/` | admin CMS | `/opt/delno/admin` |
| `DELNO-site-v23/` | marketing site | `/opt/delno/site` |
| `delno-office/*` | knowledge/mail/files/calendar/conference | `/opt/delno/{…}` |
| `delno-api/deploy/docker-compose.stack.yml` | compose | `/opt/delno/docker-compose.yml` |
| `delno-api/.env.example` | шаблон секретов | → `/opt/delno/.env` |
| `delno-api/deploy/nginx-*.conf` | HTTP/HTTPS/SNI mux | `/etc/nginx/…` |
| `docs/DLNO_DOMAINS.md` | DNS | reg.ru |

Параллельно в том же репо: Quantum Office brokers (`outreach/`, `mailer/`, `text-bot/`, `console/`, …) для `/opt/ava-*` / `qo-*`.

---

## Быстрый restore (Cloud4Box)

```bash
# 1) код
git clone https://github.com/ryabichello-stack/quantum-office.git /tmp/qo
cd /tmp/qo
git checkout <release-or-main-branch>

# 2) разложить в /opt/delno + nginx
bash delno-api/deploy/restore_cloud4box.sh

# 3) секреты (НЕ из git)
cp /opt/delno/.env.backup /opt/delno/.env   # или заполнить из .env.example
chmod 600 /opt/delno/.env

# 4) поднять
RUN_COMPOSE=1 bash delno-api/deploy/restore_cloud4box.sh

# 5) SSL если нет сертификата
mkdir -p /var/www/certbot
certbot certonly --webroot -w /var/www/certbot \
  -d dlno.ru -d www.dlno.ru -d api.dlno.ru -d app.dlno.ru \
  -d admin.dlno.ru -d cdn.dlno.ru -d wiki.dlno.ru -d status.dlno.ru \
  -d zntn.ru -d www.zntn.ru
ln -sf /etc/nginx/sites-available/dlno.ru.ssl.conf /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

DNS: см. [`DLNO_DOMAINS.md`](DLNO_DOMAINS.md) — apex A → `161.104.89.123`.

---

## Порты (после restore)

| Сервис | Host port |
|--------|-----------|
| site | 18019 |
| api | 18020 |
| knowledge | 18021 |
| web cabinet | 3020 |
| admin | 3010 |
| mail/files/cal/conf | 18000/18015/18014/18016 |
| nginx HTTPS (internal) | 4444 |
| SNI mux / Reality | 443 → 4444 or 8443 |

---

## Что НЕ в git

- `/opt/delno/.env`, JWT, OpenAI, SMTP, OAuth tokens  
- Postgres volume / brain SQLite data  
- Let’s Encrypt private keys (перевыпускаются certbot)  
- 3x-ui / Reality client keys  

Бэкап секретов и PG — отдельно (шифрованный offsite), не в GitHub.

---

## Smoke после restore

```bash
curl -sf https://api.dlno.ru/health
curl -sfI https://app.dlno.ru/ | head -3
curl -sfI https://dlno.ru/ | head -3
docker compose -f /opt/delno/docker-compose.yml ps
```

---

## Дисциплина

1. Любое прод-изменение кода → commit + push + PR.  
2. Секреты только в `.env` на сервере.  
3. Перед «ломающим» деплоем: `cp -a /opt/delno/.env /root/backups/delno.env.$(date +%Y%m%d)`.
