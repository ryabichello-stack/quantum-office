# DELNO — домены (production)

**Купленный домен бренда:** **dlno.ru** — здесь открывается публичный проект DELNO.

---

## Целевая схема

| Домен | Назначение | Backend (prod server) |
|-------|------------|------------------------|
| **https://dlno.ru** | Marketing site (Product P1) | `delno-site-root` → `127.0.0.1:18022` |
| **https://www.dlno.ru** | → redirect / same as dlno.ru | nginx |
| **https://api.dlno.ru** | DELNO Platform API | `delno-api` → `127.0.0.1:18020` |
| https://app.dlno.ru | Личный кабинет (delno-web) | позже |
| https://admin.dlno.ru | Admin + CMS (delno-admin) | позже |

**Staging (внутренний):** https://a.47z.ru/delno/ · https://a.47z.ru/delno-api/

---

## Статус на сервере `5.35.86.62` (2026-09-01)

| Компонент | Статус |
|-----------|--------|
| nginx vhost `dlno.ru` | ✅ `/etc/nginx/sites-enabled/dlno.ru.conf` |
| Site root (без `/delno`) | ✅ Docker `delno-site-root` :18022 |
| API | ✅ `delno-api` :18020 |
| Прямая проверка | ✅ `curl --resolve dlno.ru:80:5.35.86.62` → наш Next.js DELNO |

Deploy script: `delno-api/deploy/install_dlno_ru.sh`

---

## Cloudflare (нужно с вашей стороны)

Сейчас **dlno.ru** в Cloudflare указывает на **старый хостинг** (OpenAI Sites / Vite), не на наш сервер.

### Шаги

1. [Cloudflare Dashboard](https://dash.cloudflare.com) → домен **dlno.ru** → **DNS**
2. Записи:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `@` | `5.35.86.62` | Proxied ☁️ |
| A или CNAME | `www` | `5.35.86.62` или `dlno.ru` | Proxied |
| A | `api` | `5.35.86.62` | Proxied |

3. **SSL/TLS** → Overview → режим **Full** (или Full strict после origin cert)
4. Удалить / отключить записи на старый origin (если есть CNAME на `*.oaiusercontent.com` и т.п.)

### Проверка после смены DNS

В браузере https://dlno.ru — в исходном коде страницы должны быть пути `/_next/static/...`, не `/assets/index-...`.

```bash
curl -sI https://dlno.ru | head -5
curl -s https://dlno.ru | grep -o '_next/static' | head -1
```

---

## SSL на origin

На сервере certbot пока не установлен. Варианты:

- **A.** Cloudflare **Full** + self-signed на nginx (быстро)
- **B.** Cloudflare Origin Certificate → nginx (рекомended с Full strict)
- **C.** `certbot --nginx` после того как DNS смотрит на сервер

---

## Email бренда

На сайте v4: `office@dlno.ru` — настроить MX/почту отдельно (не блокирует запуск сайта).
