# Second Brain — поэтапный roadmap (без потери данных)

Связан с: [`ADR-0001-second-brain.md`](./ADR-0001-second-brain.md)  
**План до идеала (БД · граф · vault · агенты):** [`SECOND_BRAIN_IDEAL_PLAN.md`](./SECOND_BRAIN_IDEAL_PLAN.md)

**Статус ADR:** Accepted with required security amendments (2026-07-23)  
**Правило:** каждый этап обратим; legacy `:8017` `/api/knowledge/*` остаётся до отдельного approval на switch.  
**Security principle:** ACL обеспечивается инфраструктурой до LLM, не промптом.

Утверждённые выборы v1: **pgvector**; **runtime: SQLite write + Postgres/pgvector search** (`BRAIN_STORE=postgres`); **Vault в `quantum-brain`**; **physical public/private zones**; **default deny**; **manual publish only**.

**Product mission:** операционная память офиса — контакты, переписки in/out, проекты/обсуждения, файлы на сервере + FAQ.

**Реализация в office-репо (shipped v1):** пакет `knowledge/brain_platform/` + `/api/brain/*` на `ava-knowledge` (additive). Ingest: FAQ, files, IMAP mail (idempotent/dedupe). Hybrid search + embed-backfill. Text-bot SoT=brain. Voice tools **ещё на legacy**.

---

## Phase 0 — Security foundation + freeze (без смены production runtime)

**Цель:** зафиксировать SoT «как есть» + контракты безопасности. **Не** менять поведение `:8017` / voice / text.

### Работы
1. Снимок `quantum_labs.md` → `knowledge/vault/legacy/quantum_labs.v1.md` (+ sha256).
2. Снимок `index.yaml` → `vault/legacy/index.v1.yaml`.
3. `import-manifest` (скелет): H2/H3 + предложенный `type` / `visibility` / ACL / classification.
4. JSON Schema / pydantic: `tenant_id`, ACL, classification, publication, `ai_processing`, chunk metadata.
5. Service principals + default-deny policies (`voice-public`, `voice-office`, `text-secretary`, `outreach`, `cursor-admin`).
6. Contract tests + **negative-security tests** (post-filter-only запрещён концептуально; restricted без allow-list; cache key; audit redaction; public publish).
7. Документировать dual-path и план переноса канона в `quantum-brain`.

### Не делаем
- Смена поискового движка на проде  
- Переключение voice/text на новую платформу  
- Embeddings / graph runtime  

### Тесты / проверки
- diff sha256 legacy == content MD в git  
- `POST :8017/query` smoke без изменений поведения (prod)  
- pytest: schema + negative-security  

### Rollback
- ничего не меняли в runtime → N/A  

### Exit criteria
- [x] ADR Accepted with security amendments  
- [ ] Манифест покрывает 100% секций монолита (черновик есть)  
- [ ] Contract + negative-security tests зелёные  
- [ ] Отдельный approval на дальнейшие фазы / switch агентов  

---

## Phase 1 — Platform skeleton + Vault repo bootstrap

**Цель:** `knowledge/platform/` + репозиторий `quantum-brain` с `_meta/`; runtime `:8017` ещё на legacy.

### Работы
1. Создать private repo `quantum-brain` с деревом `vault/` + `_meta/` (taxonomy, acl-roles, service-principals).
2. В office-репо: `platform/` пакеты Permission, Safety, schemas; CI validate.
3. JSON Schema / pydantic обязательны: `tenant_id`, ACL, publication.
4. Compat: runtime `:8017` **продолжает** читать legacy MD.

### Exit criteria
- [ ] CI валидирует schema  
- [ ] Legacy query e2e зелёный  
- [ ] `quantum-brain` private, без копирования secrets в office image  

---

## Phase 2 — Миграция контента (шардинг без удаления)

**Цель:** разрезать монолит на документы **копированием** в `quantum-brain`.

### Стратегия нарезки
| Источник (пример) | Цель | visibility (черновик) |
|--------------------|------|------------------------|
| FAQ / продукт | `products/quantum-payouts/faq/*.md` | `company` (+ channel `assistant-safe` после review) |
| Legal / «не обещать» | `products/quantum-payouts/legal/*.md` | `team:sales` или `restricted` |
| AVA contacts / ops | `products/ava/ops/*.md` | `team:ops` / `restricted` |
| Call scripts | `products/quantum-payouts/playbooks/*.md` | `team:sales` |
| Неясно / sensitive | `vault/legacy/unsorted/*.md` | `restricted` + allow-list |

`public` — **только** после manual publish approval.  
Каждый шард: полный security frontmatter + `source: legacy/...#anchor`.

### Работы
1. Авто-сплит по H2/H3 + ручной review.  
2. Feature flag `KNOWLEDGE_READ_MODE=legacy|dual_compare|brain` (prod cutover: `brain` with legacy fallback).  
3. Safety scan на каждый импорт → quarantine при credentials.

### Тесты
- Нет потери символов (shards + legacy ≥ legacy)  
- Negative ACL: guest / voice-public не видит company/restricted  
- Contract: voice/mailer response shape на compat path  

### Rollback
- `KNOWLEDGE_READ_MODE=legacy`  

---

## Phase 3 — Permission Service + in-query ACL

**Цель:** ACL реально фильтрует **внутри** FTS / (позже) vector / graph.

### Работы
1. `PermissionService`: principal → mandatory SQL/filter predicate (`tenant_id` + ACL).  
2. Маппинг service principals (см. ADR §4.12); default **deny**.  
3. Post-filter только как defense-in-depth.  
4. Audit log: redacted preview / query hash, doc ids, denied count.  
5. Cache keys: tenant + principal + groups + permission_revision + index_revision.  
6. Negative tests: secret/restricted never in voice-public retrieve; unknown principal → empty.

### Exit criteria
- [ ] Набор ACL e2e красный→зелёный  
- [ ] Compat API с explicit principal (не «весь корпус»)  

---

## Phase 4 — Indexer + safety + physical indexes

**Цель:** pipeline + `knowledge_public` / `knowledge_private`.

### Pipeline
```
MD change → Safety scan → Classify → Normalize → Chunk(inherit ACL) →
  Embed(по ai_processing) → Upsert FTS/Vector/Graph (tenant+ACL) → Ready
  OR quarantine
```

### Работы
1. Chunkers + обязательные chunk fields (`tenant_id`, `acl_revision`, …).  
2. Транзакционное обновление ACL документа → chunks.  
3. Manual publish → копирование в public index.  
4. Отдельные credentials: public services без доступа к private.

### Exit criteria
- [ ] `kb index` идемпотентен  
- [ ] Credential doc → quarantine, не в индексе  
- [ ] voice-public credentials не открывают private DB/index  

---

## Phase 5 — Vector (pgvector) + Hybrid search

**Цель:** semantic + hybrid на pgvector с in-query ACL.

### Работы
1. Interface `VectorStore` + реализация **pgvector only** в v1.  
2. Embedding provider pluggable + AI processing policy.  
3. Modes: `keyword | semantic | hybrid` (RRF), все с ACL в запросе.  
4. Qdrant — **не** внедрять до измеримой perf-проблемы.

### Exit criteria
- [ ] Смена backend = конфиг (абстракция готова)  
- [ ] Hybrid ≥ keyword на регрессионном наборе  
- [ ] Restricted/secret не уходят во внешний embedding API  

---

## Phase 6 — Entity Graph + Contact Directory (Postgres)

**Цель:** граф сущностей с **контактами в центре** (email, телефон, должность, компания) и связями с проектами/письмами.

### Работы
1. Таблицы ADR §4.15 (`entities`, `edges`, `contacts`, `threads`, …).  
2. Extractor: frontmatter + mail headers + LLM propose **только** если policy позволяет.  
3. API/MCP: `kb.find_contact`, `related`, timeline; ACL в SQL.  
4. ПДн: `contains_personal_data`; default не public.  

### Exit criteria
- [ ] Найти человека по email/телефону/компании  
- [ ] Демо-граф: контакт → компания → проект → thread → файл  
- [ ] Guest / voice-public не видит ПДн и private edges  

---

## Phase 6b — Continuous operational ingest (mail + server files)

**Цель:** база **растёт** из реальной работы офиса — главная продуктовая задача.

### Работы
1. **Mail Ingestor:** входящие + исходящие (Message-ID идемпотентность) → `email_thread` docs + upsert contacts.  
2. **File Ingestor:** разрешённые roots на сервере + вложения → `FileAsset` + index.  
3. Project/discussion notes → связь с `Project` entity.  
4. Watcher/cron; safety scan на каждое сообщение/файл.  
5. Cursor (`cursor-admin` + personal auth) и office principals ищут по почте/файлам в пределах ACL.  

### Не делаем
- Отдача всей почты в `voice-public`  
- External embedding для писем с ПДн/секретами без policy  

### Exit criteria
- [ ] Новый входящий/исходящий letter появляется в поиске после ingest  
- [ ] Контакты из писем обновляют directory  
- [ ] Файл на сервере (в allowlisted root) находится по содержанию/имени при ACL  
- [ ] Ответ на типовой рабочий вопрос = retrieve по FAQ + thread + contact + file  

---

## Phase 7 — RAG + MCP Gateway

**Цель:** единая память для агентов («ответить на любой рабочий вопрос»); **switch voice/text — отдельный approval**.

### Работы
1. `RAG.retrieve(query, principal, token_budget)` across FAQ + mail + files + contacts.  
2. MCP: `kb.search`, `kb.get`, `kb.related`, `kb.find_contact`, `kb.list_threads`, `kb.upsert`, `kb.reindex`, `kb.ingest_status`.  
3. Подключение агентов только после explicit approval.  

### Exit criteria
- [ ] Cursor успешно отвечает на рабочий вопрос из почты/контактов/файлов с ACL  
- [ ] Voice/text не переключены без approval gate  

---

## Phase 8 — Admin UI + publish workflow

**Цель:** browse, ACL, reindex, **publish approval**, quarantine review, contact merge, ingest monitors.

---

## Чеклист владельца (актуализирован)

1. [x] Accept ADR-0001 with security amendments  
2. [x] Vault → отдельный `quantum-brain`  
3. [x] Vector v1 → pgvector  
4. [x] Graph v1 → Postgres  
5. [x] Service principals + default deny + assistant-safe  
6. [x] Product mission: contacts + mail + files + projects (operational memory)  
7. [ ] Phase 0 tests зелёные  
8. [ ] Создать private repo `quantum-brain`  
9. [ ] Утвердить mailbox accounts + server file roots для ingest  
10. [ ] Отдельный approval на switch voice/text  

---

## Что сознательно не делаем «сразу»

- Не удаляем `quantum_labs.md` и не выключаем keyword `:8017`  
- Не переключаем voice/text на Second Brain без approval  
- Не даём voice/text blanket `company` / всю почту  
- Не авто-publish в `public` (особенно ПДн и переписку)  
- Не шлём restricted/secret во внешний embedding API  
- Не внедряем Qdrant / Neo4j в v1  
- Не кешируем только по тексту запроса  
- Не пишем полный чувствительный query в обычный audit log  

---

## Краткая оценка готовности текущего `knowledge/`

| Требование Second Brain | Готовность | Комментарий |
|-------------------------|------------|-------------|
| Ответ на любой рабочий вопрос | 🟡 | FAQ+mail+files hybrid; graph/citations ещё нет |
| Контакты (email/телефон/должность/компания) | 🟢 | Ingest + API/tools |
| Переписки in/out | 🟢 | IMAP ingest + threads |
| Файлы на сервере | 🟢 | file ingest roots |
| Проекты / обсуждения | 🟡 | threads/topics; graph expand нет |
| MD FAQ как SoT слой | 🟡 | unified `quantum_labs.md`; vault repo ещё нет |
| Tenant + ACL + classification | 🟢 | in-query ACL |
| Physical public/private | 🔴 | Закреплено в ADR |
| Entity graph + contacts | 🔴 | tables in PG schema; API later |
| Semantic/Hybrid (pgvector) | 🟡 | cutover `BRAIN_STORE=postgres` |
| Safety / quarantine | 🟡 | Контракты Phase 0 |
| LLM-agnostic MCP | 🟡 | Cursor MCP stdio + REST `/api/brain/*` |
| Compat для агентов | 🟢 | Voice/text на общем API; switch заблокирован |

**Вывод:** Second Brain на проде — операционная память + hybrid search; cutover search на Postgres/pgvector. Дальше: physical zones, vault, graph API, voice switch.
