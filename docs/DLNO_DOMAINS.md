# DELNO — домены (production)

**Revision:** REV-4.0 · 2026-11-12  
**Купленный домен бренда:** **dlno.ru**  
**Prod (Cloud4Box):** **`161.104.89.123`**

> Beget `5.35.86.62` уничтожен — не использовать в DNS.

---

## Регистратор и DNS (reg.ru)

| Параметр | Значение |
|----------|----------|
| Регистратор | **reg.ru** |
| NS | `ns1.reg.ru`, `ns2.reg.ru` |
| Prod server IP | **`161.104.89.123`** |
| Удалить | `doc.dlno.ru` — не нужен |

### Записи DNS (целевая схема)

| Type | Name | Value | Примечание |
|------|------|-------|------------|
| **A** | `@` | `161.104.89.123` | apex |
| **CNAME** | `www` | `dlno.ru` | → 301 на apex |
| **CNAME** | `api` | `dlno.ru` | delno-api |
| **CNAME** | `app` | `dlno.ru` | delno-web |
| **CNAME** | `admin` | `dlno.ru` | delno-admin |
| **CNAME** | `wiki` | `dlno.ru` | placeholder |
| **CNAME** | `cdn` | `dlno.ru` | static / widget |
| **CNAME** | `status` | `dlno.ru` | placeholder |

Дополнительно (бренд):

| Type | Name | Value |
|------|------|-------|
| **A** | `zntn.ru` `@` | `161.104.89.123` |
| **CNAME** | `www` (zntn) | `zntn.ru` → 301 на `https://dlno.ru` |

> Cloudflare proxy не включать. `dig dlno.ru` → `161.104.89.123`.

**Ещё не на C4B:** `47z.ru` (нет A), `a.47z.ru` (всё ещё Beget) — поправить отдельно.

---

## Маршрутизация (Cloud4Box)

| Hostname | Backend | Порт |
|----------|---------|------|
| **https://dlno.ru** | `delno-site` | `127.0.0.1:18019` |
| **https://www.dlno.ru** | 301 → dlno.ru | — |
| **https://api.dlno.ru** | `delno-api` | `127.0.0.1:18020` |
| **https://app.dlno.ru** | `delno-web` | `127.0.0.1:3020` |
| **https://admin.dlno.ru** | `delno-admin` | `127.0.0.1:3010` |
| **https://cdn.dlno.ru** | `/opt/delno/cdn` | static |
| **https://wiki.dlno.ru** / **status** | placeholder | 503 |
| **https://zntn.ru** | 301 → dlno.ru | — |

### TLS / SNI mux

Публичный **:443** = nginx **stream** SNI mux:

- SNI `*.dlno.ru` / `zntn.ru` → `127.0.0.1:4444` (nginx HTTPS + Let’s Encrypt)
- иначе → `127.0.0.1:8443` (**xray Reality**, порт сдвинут с 443)

Файлы:

| Путь | Назначение |
|------|------------|
| `/etc/nginx/sites-available/dlno.ru.conf` | HTTP ACME + redirect |
| `/etc/nginx/sites-available/dlno.ru.ssl.conf` | HTTPS :4444 |
| `/etc/nginx/stream.d/sni-mux-443.conf` | SNI mux :443 |
| `/etc/letsencrypt/live/dlno.ru/` | сертификат |

Шаблоны в git: `delno-api/deploy/nginx-dlno.ru.conf`, `nginx-dlno.ru.ssl.conf`, `nginx-stream-sni-mux-443.conf`.

MCP отдельный DNS **не нужен** — `https://api.dlno.ru/v1/mcp`.

---

## Smoke

```bash
curl -sf https://api.dlno.ru/health
curl -sfI https://app.dlno.ru/ | head -5
curl -sfI https://dlno.ru/ | head -5
curl -sfI https://zntn.ru/ | grep -i location
curl -sf -o /dev/null -w '%{http_code}\n' https://wiki.dlno.ru/   # 503
```

UI env:

- `NEXT_PUBLIC_DELNO_API_URL=https://api.dlno.ru`

---

## Email бренда (Reg.ru hosting)

| | |
|--|--|
| Ящик | `office@dlno.ru` |
| MX | `mx1.hosting.reg.ru` / `mx2.hosting.reg.ru` |
| SMTP | `mail.hosting.reg.ru:465` (SSL), логин = полный адрес |
| IMAP | `mail.hosting.reg.ru:993` |

Env на Cloud4Box (`/opt/delno/.env`): `MAIL_*` + `LEAD_SMTP_*` — **не** `smtp.mail.ru` / `office@quantumlabs.ru` (это почта Quantum Labs).

Пароль ящика в Beget-архиве не найден — задать в панели Reg.ru и прописать `MAIL_PASSWORD` / `LEAD_SMTP_PASSWORD`.
