# DELNO — изолированный деплой

DELNO живёт **отдельно** от Quantum Office, Polyhub, AVA и outreach. Цель: не мешать другим продуктам и перенести на другой сервер одной папкой.

## Принципы

| Правило | Реализация |
|---------|------------|
| Свой каталог | `/opt/delno/` — site, api, data, .env |
| Своя Docker-сеть | `delno-internal` (не default bridge) |
| Своя БД | PostgreSQL только в compose DELNO, volume `delno-pg-data` |
| Свои порты (localhost) | site `18019`, api `18020`, pg **не** наружу |
| Свои секреты | `/opt/delno/.env` — **не** читать `/opt/ava-*` |
| Nginx | только `/delno/`, `/delno-api/` — до catch-all Polyhub |
| systemd | `delno-stack.service` — без `Wants=ava-*` |
| Adapters | опциональны через env; по умолчанию **выключены** |

## Структура на сервере

```
/opt/delno/
├── .env                    # единственный источник секретов DELNO
├── docker-compose.yml
├── site/                   # исходники / build context delno-site
├── api/                    # исходники delno-api
└── data/                   # резервные дампы (опционально)
```

## Порты (не пересекаются с ava 8011–8018, polyhub 13000+)

| Сервис | Host bind |
|--------|-----------|
| delno-site | `127.0.0.1:18019` |
| delno-api | `127.0.0.1:18020` |
| delno-postgres | только docker internal |

## Перенос на другой сервер

```bash
# на старом
cd /opt/delno && docker compose down
tar czf delno-migrate.tgz /opt/delno /etc/systemd/system/delno-stack.service
# nginx snippet — вручную или из deploy/nginx-delno.conf.snippet

# на новом
tar xzf delno-migrate.tgz -C /
cd /opt/delno && docker compose up -d --build
nginx -t && systemctl reload nginx
```

Меняется только DNS/nginx и `.env` (adapter URLs если нужны).

## Что не трогаем

- `/opt/ava-*`, `/opt/polyhub`, `/root/ava`
- общие `.env` других сервисов
- порты и systemd units других продуктов

## Adapters (временная связь с Quantum Office)

Только явные URL в `/opt/delno/.env`:

```env
# пусто = DELNO автономен, KB fallback
KNOWLEDGE_BASE_URL=
MESSENGER_BASE_URL=
```

При переносе на отдельный сервер adapters указывают на новые delno-knowledge / delno-channels или остаются пустыми.
