# DELNO — домены (production)

**Revision:** REV-3.2 · 2026-09-01  
**Купленный домен бренда:** **dlno.ru** — публичный marketing site DELNO.

---

## Регистратор и DNS

| Параметр | Значение |
|----------|----------|
| Регистратор | **reg.ru** |
| NS | `ns1.reg.ru`, `ns2.reg.ru` |
| Prod server IP | `5.35.86.62` |
| Статус DNS | ⏸ **отложено** — dev на staging; A-записи настроит владелец позже |

> **Не Cloudflare.** Старые версии этого файла описывали Cloudflare — это устарело.

---

## Целевая схема

| Домен | Назначение | Backend (prod server) |
|-------|------------|------------------------|
| **https://dlno.ru** | Marketing site (Product P1) | `delno-site-root` → `127.0.0.1:18022` |
| **https://www.dlno.ru** | → redirect / same as dlno.ru | nginx |
| **https://api.dlno.ru** | DELNO Platform API | `delno-api` → `127.0.0.1:18020` |
| https://app.dlno.ru | Личный кабинет (delno-web) | позже |
| https://admin.dlno.ru | Admin + CMS (delno-admin) | позже |

**Staging (сейчас):** https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/

---

## Статус на сервере `5.35.86.62`

| Компонент | Статус |
|-----------|--------|
| nginx vhost `dlno.ru` | ✅ `/etc/nginx/sites-enabled/dlno.ru.conf` |
| Site staging (basePath `/delno`) | ✅ Docker `delno-site` :18019 |
| Site root (без `/delno`) | ✅ Docker `delno-site-root` :18022 — **пересборка отстаёт от staging** |
| API | ✅ `delno-api` :18020 |
| Knowledge | ✅ `delno-knowledge` :18021 |
| Postgres | ✅ `delno-postgres` (internal only) |

Deploy scripts: `delno-api/deploy/install_dlno_ru.sh`, `install_site_staging.sh`, `install_full_stack_prod.sh`

---

## DNS — когда будете включать (reg.ru)

1. [reg.ru](https://www.reg.ru) → домен **dlno.ru** → DNS / зона
2. Записи:

| Type | Name | Content | TTL |
|------|------|---------|-----|
| A | `@` | `5.35.86.62` | 300–3600 |
| A | `www` | `5.35.86.62` | 300–3600 |
| A | `api` | `5.35.86.62` | 300–3600 |

3. Дождаться propagation (обычно до нескольких часов)
4. SSL на origin (см. ниже)
5. Smoke:

```bash
curl -sf https://dlno.ru/ | head -c 200
curl -sf https://api.dlno.ru/v1/health
curl -sf -X POST https://dlno.ru/api/leads \
  -H 'Content-Type: application/json' \
  -d '{"source":"dns-smoke","name":"Test","phone":"+79990001122"}'
```

В исходном коде страницы должны быть пути `/_next/static/...`, не legacy `/assets/index-...`.

---

## SSL на origin

На сервере certbot пока не установлен. Варианты без Cloudflare:

- **A.** `certbot --nginx -d dlno.ru -d www.dlno.ru -d api.dlno.ru` после того как A-записи смотрят на сервер
- **B.** Let's Encrypt через reg.ru (если доступен в панели)
- **C.** Временно HTTP-only на origin + redirect (не для prod marketing)

---

## CORS / env после DNS

В `/opt/delno/.env` и nginx проверить:

- `CORS_ORIGINS` включает `https://dlno.ru`, `https://www.dlno.ru`
- Site container: `DELNO_API_URL=http://api:8020` (internal)
- Prod site root rebuild с `NEXT_PUBLIC_BASE_PATH=""` или `/`

---

## Email бренда

На сайте v4: `office@dlno.ru` — MX/почту настроить отдельно (не блокирует запуск сайта).
