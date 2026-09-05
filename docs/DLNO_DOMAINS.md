# DELNO — домены (production)

**Revision:** REV-3.4 · 2026-09-01  
**Купленный домен бренда:** **dlno.ru**

---

## Регистратор и DNS (reg.ru)

| Параметр | Значение |
|----------|----------|
| Регистратор | **reg.ru** |
| NS | `ns1.reg.ru`, `ns2.reg.ru` |
| Prod server IP | **`5.35.86.62`** |
| Удалить | `doc.dlno.ru` — не нужен (отдельный docs.dlno.ru не планируется) |

### Записи DNS (целевая схема)

| Type | Name | Value | Примечание |
|------|------|-------|------------|
| **A** | `@` | `5.35.86.62` | apex |
| **CNAME** | `www` | `dlno.ru` | → 301 на apex (nginx) |
| **CNAME** | `api` | `dlno.ru` | delno-api |
| **CNAME** | `app` | `dlno.ru` | delno-web |
| **CNAME** | `admin` | `dlno.ru` | delno-admin |
| **CNAME** | `wiki` | `dlno.ru` | placeholder → будущий Wiki |
| **CNAME** | `cdn` | `dlno.ru` | static / widget.js |
| **CNAME** | `status` | `dlno.ru` | placeholder → status page |

> **Важно:** A-запись `@` должна указывать на **`5.35.86.62`**, не на Cloudflare proxy.  
> Если `dig dlno.ru` возвращает `162.159.*` / `172.66.*` — DNS ещё не переключён или включён прокси CF.

---

## Маршрутизация (nginx → backend)

| Hostname | Назначение | Backend | Статус |
|----------|------------|---------|--------|
| **https://dlno.ru** | Marketing site DELNO | `delno-site-root` → `127.0.0.1:18022` | 🔄 deploy |
| **https://www.dlno.ru** | 301 → `https://dlno.ru` | nginx redirect | 🔄 |
| **https://api.dlno.ru** | Production API | `delno-api` → `127.0.0.1:18020` | ✅ |
| **https://app.dlno.ru** | Кабинет клиента | `delno-web` → `127.0.0.1:18023` | ✅ MVP (staging: `/delno-app/`) |
| **https://admin.dlno.ru** | Admin / CMS | `delno-admin` → `127.0.0.1:18024` | 🔄 scaffold |
| **https://wiki.dlno.ru** | Wiki / docs для клиентов | placeholder **503** | ⬜ не продукт |
| **https://cdn.dlno.ru** | Статика, widget.js | `/opt/delno/cdn` (nginx static) | ⬜ не продукт |
| **https://status.dlno.ru** | Status page | placeholder **503** | ⬜ не продукт |

**Staging (без изменений):** https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/

Поддомены **не** сливаются в один маркeting site — у каждого свой `server_name` в nginx.

---

## Файлы на сервере

| Путь | Назначение |
|------|------------|
| `/etc/nginx/sites-available/dlno.ru.conf` | vhosts всех hostnames |
| `/opt/delno/ingress/wiki/` | placeholder HTML (503) |
| `/opt/delno/ingress/status/` | placeholder HTML (503) |
| `/opt/delno/cdn/` | static root для cdn.dlno.ru |
| `/opt/delno/site/` | исходники marketing (Docker build) |

**Deploy:** `delno-api/deploy/install_dlno_ingress.sh`  
**Smoke:** `delno-api/deploy/smoke_dlno_ingress.sh`  
**Nginx template:** `delno-api/deploy/nginx-dlno.ru.conf`

---

## SSL (Let's Encrypt)

После того как DNS `@` и CNAME смотрят на `5.35.86.62`:

```bash
apt install -y certbot python3-certbot-nginx   # если ещё нет
bash /opt/delno/deploy/install_dlno_ingress.sh
```

Certbot запрашивает сертификат для:

`dlno.ru`, `www.dlno.ru`, `api.dlno.ru`, `app.dlno.ru`, `admin.dlno.ru`, `wiki.dlno.ru`, `cdn.dlno.ru`, `status.dlno.ru`

### Сервер `5.35.86.62`: SNI mux на :443

На этом хосте публичный **:443** занят stream SNI-мультиплексором (`/etc/nginx/stream.d/sni-mux-443.conf`) для `a.47z.ru` / Reality.  
HTTPS для `*.dlno.ru` слушает **127.0.0.1:4444**; stream проксирует по SNI:

- `dlno.ru`, `www`, `api`, `app`, `admin`, `wiki`, `cdn`, `status` → `127.0.0.1:4444`
- остальное → `127.0.0.1:4443` (`a.47z.ru`)

После `certbot --nginx` замените в `dlno.ru.conf` `listen 443 ssl` на `listen 127.0.0.1:4444 ssl http2` (и `[::1]:4444`), затем `nginx -t && systemctl reload nginx`.

Проверка:

```bash
curl -sfI https://dlno.ru/ | head -5
curl -sf https://api.dlno.ru/v1/health
curl -sfI https://www.dlno.ru/ | grep -i location   # → https://dlno.ru/
USE_HOST=1 bash /opt/delno/deploy/smoke_dlno_ingress.sh
```

---

## Smoke checklist (после DNS + SSL)

```bash
curl -sf https://dlno.ru/ | head -c 200
curl -sf https://api.dlno.ru/v1/health
curl -sfI https://www.dlno.ru/ | grep -i location
curl -sf -o /dev/null -w '%{http_code}\n' https://wiki.dlno.ru/    # 503
curl -sf -o /dev/null -w '%{http_code}\n' https://status.dlno.ru/  # 503
curl -sf https://app.dlno.ru/ | head -c 100
curl -sf -o /dev/null -w '%{http_code}\n' -H "Host: admin.dlno.ru" http://127.0.0.1/   # 307 → /login
```

---

## CORS / env

UI containers:

- `NEXT_PUBLIC_DELNO_API_URL=https://api.dlno.ru` (app, admin)

Site root:

- `DELNO_API_URL=http://api:8020` (internal docker network)
- `NEXT_PUBLIC_BASE_PATH=` (empty — root, не `/delno`)

---

## Email бренда

`office@dlno.ru` — MX настроить отдельно в reg.ru (не блокирует сайт/API).
