# DELNO — аудит: Conversation-driven Onboarding

**Revision:** ONBOARDING-AUDIT-1.0 · **2026-09-04**  
**Ветка:** `cursor/delno-api-scaffold-14e9`  
**Связано:** [`DELNO_FOR_CHATGPT.md`](DELNO_FOR_CHATGPT.md) REV-4.7 · [`DELNO_WIDGET_AUDIT.md`](DELNO_WIDGET_AUDIT.md)

**Продуктовый принцип (новый):**

> Пользователь не заполняет DELNO — он **разговаривает** с DELNO.  
> DELNO сам слушает, читает сайт/файлы, собирает draft knowledge, показывает сводку, получает подтверждение, публикует.

**Это уточнение заменяет** предыдущую идею жёстких веток Website-to-Agent / «есть сайт / нет сайта / визитка / сначала KB».

---

## 1. Executive summary

| Область | Статус | Комментарий |
|---------|--------|-------------|
| Conversation Core | ✅ | `conversations` + `messages` — переиспользовать |
| Operator + Tool Registry | ✅ | cabinet tools частично покрывают onboarding writes |
| Brain / delno-knowledge | ✅ | upsert, chunk, search, provenance — не дублировать |
| Draft → Publish (brain) | 🔄 | **Схема есть**, tenant API **не передаёт** publication |
| File upload (tenant API) | ⬜ | Только text JSON; brain имеет extract_text (PDF/DOCX/XLSX) |
| Website import | 🔄 | `website_import.py` + `instant_demo` — **отдельный REST**, не диалог |
| Onboarding UI | ⬜ | Settings wizard + KB form; **нет** chat-first onboarding |
| Source provenance E1.4 | ✅ | document_id/chunk_id в search hits — расширить metadata |
| Conflict resolution | ⬜ | Нет canonical vs conflicting sources |
| Events TTFV | 🔄 | `instant_demo.*` есть; onboarding.* — добавить |

**Вывод:** ~70% инфраструктуры уже есть. Нужен **orchestration layer** (onboarding conversation mode + draft state + file ingest API + publish confirm), не второй KB/Conversation engine.

---

## 2. Ответы на 20 вопросов аудита

### 1. Что уже существует для file upload?

| Слой | Есть? | Где |
|------|-------|-----|
| delno-api tenant multipart upload | ❌ | — |
| delno-web file input | ❌ | — |
| brain `extract_text_from_bytes` | ✅ | `delno-knowledge/brain_platform/ingest/extract_text.py` |
| brain mail/files ingest (CLI) | ✅ | admin-side, не tenant-scoped HTTP |
| Tenant blob storage | ❌ | Нет S3/local file table в delno-api |

### 2. Какие форматы реально поддерживаются сейчас?

**Tenant-facing (delno-api):** только plain text/markdown в JSON (`POST /v1/tenant/knowledge/documents`, min 20 chars).

**Brain extract_text (можно переиспользовать):**

| Формат | Поддержка |
|--------|-----------|
| TXT, MD, CSV, JSON, HTML | ✅ |
| DOCX | ✅ |
| XLSX | ✅ (листы → `\|` rows, до 8 sheets) |
| PDF | ✅ (pypdf/PyPDF2) |
| PPTX | ❌ |
| Images (OCR) | ❌ |
| XLS (legacy) | ❌ |
| ZIP | ❌ (encrypted zip detected, skip) |

### 3. Как сейчас работает KB ingest?

```
delno-api upsert_tenant_knowledge_document()
  → POST delno-knowledge /api/brain/documents/upsert
  → BrainRepository.upsert_document() — chunk, embed, FTS
  → emit knowledge.document_upserted
```

Источники вызова: tenant API, operator `upload_knowledge_snippet`, register welcome doc, **instant_demo website import**.

**Проблема:** upsert всегда `visibility=public|company`, **без** `publication.approved` → guest/widget **не видит** public docs (index_zone остаётся private).

### 4. Есть ли draft/publish model у knowledge?

**В brain — да:**

- `PublicationStatus`: `unpublished` | `pending_review` | `published` | `revoked`
- `DocumentStatus`: `draft` | `active` | ...
- Vault ingest передаёт publication frontmatter

**В tenant API — нет:**

- `documents/upsert` не принимает `publication` / `status=draft`
- Всё сразу `active`, без review workflow
- CMS (`CmsPage`) имеет draft/publish — **это не brain KB**

**Нужно добавить:** thin layer — draft docs с `publication.status=unpublished` + `visibility=company` до confirm.

### 5. Как лучше реализовать draft без второго knowledge engine?

**Рекомендация:**

1. Расширить brain `DocumentUpsertRequest` + `upsert_document()` optional params: `publication`, `status`, `index_zone`
2. delno-api wrapper: `upsert_draft_knowledge()` → `visibility=company`, `publication={status: unpublished}`, `index_zone=private`, `source=onboarding.*`
3. `publish_onboarding_knowledge()` → batch flip to `published` + `approved_by` + `public_version=1` + `index_zone=public` (HIGH_IMPACT confirm)
4. Canonical business profile draft в `tenant.settings.onboarding_draft` (JSON) **до** publish — для summary/conflicts без лишних brain roundtrips

Не создавать отдельную таблицу KB — только `tenant.settings` + brain docs с правильной publication.

### 6. Есть ли уже website ingestion/crawler code?

| Компонент | Путь | Scope |
|-----------|------|-------|
| SSRF-safe fetch + HTML parse | `delno-api/app/services/website_import.py` | **1 страница**, title/meta/h1-h3/p |
| Instant demo orchestration | `delno-api/app/services/instant_demo.py` | preview + import → KB (сразу public upsert) |
| Public preview API | `POST /v1/public/instant-demo/preview` | rate limited |
| Tenant import API | `POST /v1/tenant/instant-demo` | JWT, публикует сразу |
| Multi-page crawler | ❌ | — |
| robots.txt | ❌ | — |

**Переиспользовать** fetch/parse; **перенести** в onboarding conversation tool, не отдельную форму.

### 7. Какие модели подходят для source provenance?

**Уже есть (E1.4):** `document_id`, `chunk_id`, `title`, `source`, `citation` в search hits.

**Добавить в upsert `source` string + optional metadata JSON:**

```
source_type: website | file | conversation | manual | operator
source_url, file_name, file_id, conversation_id, message_id
uploaded_at, sheet_name, page_number (where applicable)
```

Хранить:

- brain `documents.source` (string) — уже есть
- `tenant.settings.onboarding_draft.sources[]` — для UI cards и conflict audit
- `PlatformEvent` payload — для events list

### 8. Как лучше представить onboarding state?

**Рекомендация (минимум миграций):**

```json
// tenant.settings
{
  "onboarding": {
    "status": "in_progress | summary_ready | published",
    "conversation_id": "uuid",
    "started_at": "...",
    "completed_at": null
  },
  "onboarding_draft": {
    "company_name": "...",
    "services": [...],
    "prices": [...],
    "address": "...",
    "hours": "...",
    "contacts": {...},
    "faq": [...],
    "missing_fields": ["hours", "delivery_terms"],
    "sources": [{ "type": "website", "url": "...", "document_id": "..." }],
    "conflicts": [{ "field": "price.manicure", "values": [...] }]
  }
}
```

**Conversation:** `channel="onboarding"` (или `meta.mode="onboarding"`) — одна thread на tenant.

### 9. Какие Operator tools уже можно использовать?

| Tool | Onboarding use |
|------|----------------|
| `get_knowledge` | READ — что уже в draft/published |
| `get_tenant_summary` | READ — settings, flags |
| `upload_knowledge_snippet` | SAFE_WRITE — **переключить на draft upsert** |
| `update_tenant_settings` | SAFE_WRITE — business profile fields |
| `set_feature_flag` | SAFE_WRITE — enable web_voice after publish |
| `lookup_company_by_inn` | READ — optional INN step in dialog |

### 10. Какие новые tools реально нужны?

| Tool | Class | Purpose |
|------|-------|---------|
| `inspect_onboarding_draft` | READ | Summary + missing + conflicts |
| `add_draft_knowledge` | SAFE_WRITE | Text fragment → draft brain doc |
| `parse_website_source` | SAFE_WRITE | URL → draft (wrap website_import) |
| `parse_uploaded_document` | SAFE_WRITE | file_id → extract → draft |
| `update_business_profile_draft` | SAFE_WRITE | Structured fields in settings |
| `detect_knowledge_conflicts` | READ | Compare sources |
| `publish_onboarding_knowledge` | **HIGH_IMPACT** | Draft → published for widget |

Не строить отдельный onboarding engine — расширить registry.

### 11. Как избежать дублирования Conversation?

- Один `Conversation` с `channel="onboarding"` после register
- `run_operator_turn(..., channel="onboarding")` — расширить `_generate_reply` как cabinet (setup tools + onboarding prompt)
- Website/file ingest **внутри той же conversation** — не отдельные sessions
- После publish: `onboarding.status=published`, conversation остаётся в history

### 12. Как избежать дублирования Knowledge?

- Все ingest → `upsert_tenant_knowledge_document` / brain upsert
- Draft = publication unpublished + company visibility
- Publish = один HIGH_IMPACT tool, не ручной public upsert
- Переиспользовать `extract_text_from_bytes` из brain (HTTP internal call или shared package)

### 13. Какие миграции нужны?

| Миграция | Обязательна? |
|----------|--------------|
| `onboarding_uploads` table (file metadata) | ✅ рекомендуется P4.2 |
| `conversations.channel` enum | ❌ string достаточно |
| `tenant.settings` JSONB | ❌ уже есть |
| brain API publication params | ❌ schema exists, API gap only |

**Минимальная миграция:**

```sql
CREATE TABLE onboarding_uploads (
  id UUID PRIMARY KEY,
  tenant_id UUID REFERENCES tenants(id),
  conversation_id UUID REFERENCES conversations(id),
  file_name TEXT,
  content_type TEXT,
  storage_path TEXT,
  size_bytes INT,
  parse_status TEXT,
  extracted_document_id TEXT,
  meta JSONB,
  created_at TIMESTAMPTZ
);
```

Файлы: tenant-scoped path `/data/onboarding/{tenant_id}/{uuid}` на prod volume.

### 14. Какие endpoint'ы нужны?

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | `/v1/tenant/onboarding/start` | JWT | Create onboarding conversation |
| POST | `/v1/tenant/onboarding/message` | JWT | Chat turn (or reuse `/operator/chat?channel=onboarding`) |
| POST | `/v1/tenant/onboarding/upload` | JWT | Multipart file → store + parse queue |
| GET | `/v1/tenant/onboarding/status` | JWT | Draft summary, missing, conflicts |
| POST | `/v1/tenant/onboarding/publish` | JWT | Confirm → publish (or `/operator/confirm`) |

**Можно минимизировать:** только `upload` + reuse `POST /v1/operator/chat` с `channel=onboarding`.

Deprecate (UI, не API сразу): отдельная форма `POST /tenant/instant-demo` как primary UX.

### 15. Какой минимальный UI нужен?

**Новая страница:** `/dashboard/onboarding` (redirect after register вместо `/settings`)

| Element | Priority |
|---------|----------|
| Chat thread (messages) | P0 |
| Textarea + send | P0 |
| Upload button (clip) | P0 |
| File chips + parse status | P1 |
| Summary card | P1 |
| Confirm / Edit buttons | P1 |
| Drag&drop desktop | P2 |

**Не трогать сразу:** settings page можно оставить для advanced users.

### 16. Security риски

**URL import:** SSRF (частично закрыто в `website_import.py`), добавить robots.txt, page limit, domain allowlist optional.

**File upload:** size limit (10–20 MB), MIME sniff, no executables, tenant isolation, scan hook later, sanitized filenames.

**Publish:** HIGH_IMPACT confirm — wrong prices go public.

**Draft leak:** draft docs `visibility=company` — widget guest не видит до publish ✅

### 17. Разбивка на 4–6 коммитов

| # | Scope | DoD |
|---|-------|-----|
| **O1** | Audit docs + onboarding channel + draft upsert API | brain publication params; `channel=onboarding`; events `onboarding.started` |
| **O2** | Onboarding chat UI (cabinet) | Register → `/dashboard/onboarding`; reuse operator chat |
| **O3** | File upload endpoint + brain extract | PDF/DOCX/XLSX/CSV/TXT; file cards; `onboarding.file_*` events |
| **O4** | URL in conversation + graceful fallback | No error UX; missing-fields prompts |
| **O5** | Summary card + conflict detection + publish | HIGH_IMPACT confirm; widget sees published KB |
| **O6** | TTFV metrics + tests + FOR_CHATGPT sync | Scenarios A–E from spec |

### 18. Что можно сделать без риска для prod?

- O1: brain API backward-compatible optional publication fields
- O2: new onboarding page (feature-flagged)
- Docs + events only
- Draft upsert не ломает existing public widget (demo tenant)

### 19. Что потребует migration/deploy?

- O3: `onboarding_uploads` migration + volume mount
- O5: brain publish batch — deploy delno-api + delno-knowledge
- Register redirect change — deploy delno-web

### 20. Какие тесты обязательны?

| Test | Scenario |
|------|----------|
| Draft not visible to widget guest | Security |
| Publish makes KB searchable for widget | A, B |
| URL fail → conversational fallback | C |
| File upload → draft + feedback message | D |
| Price conflict → ask user | E |
| SSRF blocked | Security |
| onboarding.* events emitted | Metrics |

---

## 3. Gap vs текущий P4 Instant Demo

| Было (Commit P4) | Станет |
|------------------|--------|
| Form «URL сайта» на `/dashboard/knowledge` | URL внутри onboarding chat |
| Immediate KB publish | Draft → summary → confirm → publish |
| Single-page scrape | Same MVP scrape + dialog for gaps |
| No file upload | Upload in chat |

**API `instant-demo` оставить** как internal/tool backend, скрыть из primary UX.

---

## 4. Definition of Done (из спека)

| Scenario | Current | Target |
|----------|---------|--------|
| A — только разговор | ✅ | Onboarding channel |
| B — сайт | ✅ | In-conversation URL |
| C — сайт fail | ✅ | Conversational fallback |
| D — файл | ✅ | Upload + parse |
| E — multi-source conflict | ✅ | Conflict tool + ask |

---

## 5. DO NOT START (подтверждено)

- Site builder / визитка
- Full crawler platform
- OCR platform
- Second KB engine
- Second conversation engine
- CRM, billing, telephony, booking

---

## 6. Следующий шаг

**O1–O6 ✅ закрыты.** Следующее:

1. Deploy: `alembic upgrade head` (migration `005_onboarding_uploads`), rebuild delno-api + delno-knowledge + delno-web
2. Smoke: scenarios A–E на staging
3. P1.9 clarity test
4. E2.3 branded Telegram bot wizard
