# DELNO Widget Chat — интеграция с платформой

## Статус backend (2026-09-04)

- ✅ `POST /v1/public/widget/session|visitor|message` — реализовано в `delno-api`
- ✅ Ответы через `run_operator_turn(channel="widget")` — tenant из `site_key`
- 🔄 CDN bundle Commit 1: `widget-embed.html` + `crystal-widget.css` + `delno-widget-chat.js`
- ✅ Commit 2: rate limit, visitor bind, CORS — see `app/services/widget_security.py`

**Аудит и план:** [`../docs/DELNO_WIDGET_AUDIT.md`](../docs/DELNO_WIDGET_AUDIT.md)

## Что уже реализовано в прототипе
- Настоящее textarea-поле.
- Отправка по Enter; Shift+Enter — новая строка.
- Автоматическое увеличение textarea до 104 px.
- История сообщений.
- Панель растёт вверх, максимум 560 px / viewport-safe.
- Индикатор «печатает».
- После первого ответа DELNO спрашивает имя.
- Имя сохраняется в localStorage в демо.
- Подпись «Работает на DELNO ↗».
- Светлая, тёмная и авто-версии.
- Голосовой orb и текстовый чат используют один UI-контейнер, но пока не одну backend session.

## Как правильно связать с DELNO backend

НЕ вызывать `/v1/operator/chat` напрямую из публичного браузера.
Для виджета нужен публичный gateway, который сам определяет tenant по `site_key`.

### Рекомендуемые endpoint'ы

### 1. Создать/восстановить сессию
POST `/v1/public/widget/session`

Request:
```json
{
  "site_key": "public_site_key_from_widget_installation",
  "visitor_id": "uuid",
  "page_url": "https://client-site.ru/page",
  "referrer": "https://google.com/",
  "channel": "web"
}
```

Response:
```json
{
  "session_id": "uuid",
  "tenant_public": {
    "name": "Компания",
    "assistant_name": "DELNO"
  },
  "widget": {
    "theme": "auto",
    "collect_name": true
  }
}
```

### 2. Отправить сообщение
POST `/v1/public/widget/message`

Request:
```json
{
  "site_key": "public_site_key",
  "session_id": "uuid",
  "visitor_id": "uuid",
  "message": "Сколько стоит доставка?",
  "visitor": {
    "name": null,
    "page_url": "https://client-site.ru/",
    "referrer": null
  },
  "channel": "web"
}
```

Response:
```json
{
  "message": "Доставка стоит...",
  "next_step": "ask_name",
  "lead": {
    "id": null,
    "name": null
  },
  "sources": [
    {
      "title": "Доставка",
      "source_type": "knowledge"
    }
  ]
}
```

## Безопасность
- `site_key` — публичный идентификатор установки, НЕ tenant_id.
- backend по `site_key` сам разрешает tenant.
- браузер никогда не передаёт произвольный tenant_id.
- rate-limit на `site_key + visitor_id + IP`.
- CORS только для разрешённых доменов установки.
- session_id подписывается/проверяется backend.
- LLM не определяет tenant.
- Knowledge search строго tenant-scoped.

## Дальнейшее объединение с голосом
Одна и та же `session_id` должна использоваться:
- текстовым чатом;
- voice widget;
- будущим handoff на человека.

Тогда пользователь может спросить голосом, открыть текстовый чат и увидеть ту же историю.

## Лид
После получения имени backend обновляет lead/session:
```json
{
  "name": "Алексей"
}
```

Позже той же схемой можно запрашивать:
- телефон;
- email;
- удобное время;
но только когда сценарий реально этого требует.

## Что менять в текущем HTML
В `CONFIG.endpoint` указать:
`https://api.dlno.ru/v1/public/widget/message`

`siteKey` при установке виджета должен приходить из embed-конфига клиента.

## Embed на сторонний сайт (E3.4)

Один тег — iframe с Crystal Widget:

```html
<script
  src="https://cdn.dlno.ru/widget/v1/embed.js"
  data-site-key="PUBLIC_SITE_KEY"
  data-theme="auto"
  async
></script>
```

| Атрибут | Значение |
|---------|----------|
| `data-site-key` | публичный ключ установки (не tenant_id) |
| `data-theme` | `auto` · `light` · `dark` |
| `data-api` | опционально, default `https://api.dlno.ru/v1/public/widget` |
| `data-cdn` | опционально, default `https://cdn.dlno.ru/widget/v1` |

CDN bundle: `embed.js`, `delno-widget-client.js`, `index.html`, `light.html`, `dark.html`, `assets/`.
