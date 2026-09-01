# delno-widget

DELNO Crystal Widget **v28** — UX-прототип для embed на сайты клиентов.

| Файл | Описание |
|------|----------|
| `index.html` | theme `auto` |
| `light.html` | светлый фон |
| `dark.html` | тёмный фон |
| `assets/crystal-orb-static.webp` | orb (~15 KB) |
| `INTEGRATION.md` | backend gateway spec |

**Handoff (полное ТЗ):** [`../HANDOFF.md`](../HANDOFF.md)

## Локальный просмотр

```bash
cd delno-widget
python3 -m http.server 8090
# open http://127.0.0.1:8090/index.html
```

## Mock vs production

Прототип работает в mock-режиме без backend. Для production — публичный gateway (`/v1/public/widget/*`), **не** `/v1/operator/chat`.
