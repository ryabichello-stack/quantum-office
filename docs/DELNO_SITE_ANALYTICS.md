# DELNO: своя статистика сайта (без Метрики)

Первичная аналитика маркетингового сайта, когда Яндекс.Метрика недоступна.

## Что видит админ

URL: **https://admin.dlno.ru/analytics** (после login platform admin)

- сессии / просмотры / отказы / стр. на сессию  
- сегодня / вчера  
- график по дням  
- топ страниц и источников  
- лента последних хитов  

Периоды: 7 / 30 / 90 дней.

## Как собирается

1. На `dlno.ru` компонент `SiteAnalytics` шлёт pageview / engage / leave.  
2. Next proxy: `POST /api/analytics/hit` → `POST /v1/public/analytics/hit` (delno-api).  
3. Postgres таблица `site_pageviews` (создаётся через `create_all` при старте API).  
4. Admin API (Bearer platform_admin):
   - `GET /v1/admin/analytics/summary`
   - `GET /v1/admin/analytics/timeseries`
   - `GET /v1/admin/analytics/pages`
   - `GET /v1/admin/analytics/referrers`
   - `GET /v1/admin/analytics/recent`

IP хранится только как hash; rate limit ~120 hit/min на IP.

## Деплой

Пересобрать и перезапустить:

1. `delno-api` — новая модель + endpoints  
2. `delno-site-root` (или staging site) — трекер в layout  
3. `delno-admin` — страница `/analytics`  

Env (опционально):

- `NEXT_PUBLIC_ANALYTICS_SITE_KEY=dlno.ru` на сайте  
- `DELNO_API_URL` на сайте (уже есть)  
- `NEXT_PUBLIC_DELNO_API_URL` на admin  

Метрику можно оставить параллельно — это не замена Webvisor, а свой дашборд.
