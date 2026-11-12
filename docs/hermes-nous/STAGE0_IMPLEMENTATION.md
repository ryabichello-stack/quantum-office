# Hermes Nous — Stage 0 implementation (started)

Дата: 2026-11-13 (МСК). Ветка: `cursor/hermes-nous-runtime-9b51`.  
План-канон: [`HERMES_ORIGINAL_INTEGRATION_PLAN.md`](../HERMES_ORIGINAL_INTEGRATION_PLAN.md).

## Что сделано в этом PR

| Компонент | Путь | Статус |
|-----------|------|--------|
| Pin upstream | `delno-api/hermes_runtime/PINNED_VERSION` → **v0.23.1** | ✅ |
| Runtime image + 2-tenant lab compose | `delno-api/hermes_runtime/` | ✅ scaffold |
| HERMES_HOME templates | `hermes_runtime/templates/home/` | ✅ |
| Feature flag | `hermes_nous_runtime` (default **off**) | ✅ |
| Provision home + runtime map | `app/services/hermes_nous/provision.py` | ✅ |
| Scoped run tokens | `app/services/hermes_nous/run_tokens.py` | ✅ |
| MCP tools/list + call filter | `mcp_scope.py` + `api/v1/mcp.py` | ✅ |
| Bridge `/v1/runs` (+ chat fallback) | `bridge.py` + `api/v1/hermes_nous.py` | ✅ |
| Cabinet soft-route | `operator.py` → Nous if flag+runtime else DIY | ✅ |
| DIY archive | `docs/archive/diy-hermes/` | ✅ |
| Unit tests | `tests/test_hermes_nous_scope.py` | ✅ |

## Как посмотреть (локально)

1. Поднять lab:  
   `cd delno-api && docker compose -f hermes_runtime/docker-compose.hermes.yml up --build`  
   (нужен git + сеть; первый build долгий — клонирует pin).
2. В DELNO API: `HERMES_NOUS_RUNTIME_URL=http://127.0.0.1:18642`, `HERMES_API_SERVER_KEY=…`.
3. Включить флаг tenant: `PATCH /v1/tenant/feature-flags/hermes_nous_runtime` `{enabled:true}`.
4. `POST /v1/hermes-nous/provision` → `POST /v1/hermes-nous/runs` с сообщением.
5. Или кабинет `/v1/operator/chat` при включённом флаге.

Без живого runtime флаг можно держать выключенным — DIY loop как раньше.

## Не трогаем

Телефония / Asterisk / `trunk_id`. Prod Cloud4Box не переключаем этим PR автоматически.

## Дальше (Stage 1)

- Реально собрать image на staging и прогнать A/B isolation
- Записать digest образа
- Подключить read-only MCP grants из connector tables
- UI progress из `/v1/runs/{id}/events`
