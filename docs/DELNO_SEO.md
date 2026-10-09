# SEO — dlno.ru + Yandex

## На сайте (Next.js)

| Файл | Назначение |
|------|------------|
| `app/sitemap.ts` | `/sitemap.xml` |
| `app/robots.ts` | `/robots.txt` |
| `lib/buildMetadata.ts` | title, description, canonical, Open Graph |
| `components/SeoJsonLd.tsx` | Organization + SoftwareApplication + FAQ |
| `NEXT_PUBLIC_SITE_URL` | `https://dlno.ru` (prod) |
| `NEXT_PUBLIC_YANDEX_VERIFICATION` | meta verification из Вебmaster (после bootstrap) |

Проверка после деплоя:

```bash
curl -sf https://dlno.ru/robots.txt
curl -sf https://dlno.ru/sitemap.xml | head
```

## Mailer API (marketing OAuth)

Нужен `yandex_marketing_oauth_tokens.json` — см. `docs/YANDEX_OAUTH_MARKETING.md`.

| Endpoint | Действие |
|----------|----------|
| `GET /yandex/wordstat/phrases?token=…` | Сиды DELNO → topRequests Вордstata |
| `GET /yandex/wordstat/phrases?token=…&seeds=фраза1,фраза2` | Свои фразы |
| `GET /yandex/webmaster/bootstrap?token=…` | Добавить `https://dlno.ru/`, verification, sitemap (если verified) |
| `GET /yandex/metrika/ensure?token=…&site=dlno.ru` | Счётчик Метрики |

Wordstat: в OAuth приложении право `wordstat:api`, scope в `.env`, заявка в поддержку Директа (логин + ClientId). После одобрения — `GET /yandex/wordstat/phrases`. Если legacy endpoint недоступен (TLS/404), ждём активации доступа или подключаем Yandex Cloud Search API v2 отдельно.

## Порядок на prod

1. OAuth marketing token (verification code).
2. `bash /opt/delno/deploy/sync_metrika_and_site.sh` — счётчик на сайте.
3. `curl "http://127.0.0.1:8000/yandex/webmaster/bootstrap?token=$WEBHOOK_TOKEN"` — Вебmaster.
4. Прописать `NEXT_PUBLIC_YANDEX_VERIFICATION` из ответа verification → rebuild site.
5. `curl "http://127.0.0.1:8000/yandex/wordstat/phrases?token=$WEBHOOK_TOKEN"` — подобрать фразы → обновить `lib/seoKeywords.ts` / meta description.
