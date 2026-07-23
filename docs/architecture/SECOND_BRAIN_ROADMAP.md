# Second Brain — поэтапный roadmap (без потери данных)

Связан с: [`ADR-0001-second-brain.md`](./ADR-0001-second-brain.md)  
**Статус ADR:** Accepted with required security amendments (2026-07-23)  
**Правило:** каждый этап обратим, имеет тесты и критерий «можно откатиться на legacy `:8017` keyword».  
**Security principle:** ACL обеспечивается инфраструктурой до LLM, не промптом.

Утверждённые выборы v1: **pgvector**, **Postgres graph**, **Vault в `quantum-brain`**, **physical public/private**, **default deny**, **manual publish only**.

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
2. Feature flag `KNOWLEDGE_READ_MODE=legacy|vault|dual` (ещё не включать на voice без approval).  
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

## Phase 6 — Entity Graph (Postgres)

**Цель:** entities/edges в Postgres с tenant + visibility.

### Работы
1. Таблицы ADR §4.15.  
2. Extractor: frontmatter + LLM propose **только** если policy позволяет.  
3. API: `related`, timeline; ACL в SQL.  

### Exit criteria
- [ ] Демо-граф Quantum Payouts → банк → номинальный счёт → meeting  
- [ ] Guest / voice-public не видит edges на secret/private nodes  

---

## Phase 7 — RAG + MCP Gateway

**Цель:** единая память для агентов; **switch voice/text — отдельный approval**.

### Работы
1. `RAG.retrieve(query, principal, token_budget)`.  
2. MCP: `kb.search`, `kb.get`, `kb.related`, `kb.upsert`, `kb.reindex`.  
3. Подключение агентов только после explicit approval.  

### Exit criteria
- [ ] Cursor ищет через MCP с ACL  
- [ ] Voice/text не переключены без approval gate  

---

## Phase 8 — Admin UI + publish workflow

**Цель:** browse, ACL, reindex, **publish approval**, quarantine review.

---

## Чеклист владельца (актуализирован)

1. [x] Accept ADR-0001 with security amendments  
2. [x] Vault → отдельный `quantum-brain`  
3. [x] Vector v1 → pgvector  
4. [x] Graph v1 → Postgres  
5. [x] Service principals + default deny + assistant-safe  
6. [ ] Phase 0 tests зелёные  
7. [ ] Создать private repo `quantum-brain`  
8. [ ] Отдельный approval на switch voice/text  

---

## Что сознательно не делаем «сразу»

- Не удаляем `quantum_labs.md` и не выключаем keyword `:8017`  
- Не переключаем voice/text на Second Brain без approval  
- Не даём voice/text blanket `company`  
- Не авто-publish в `public`  
- Не шлём restricted/secret во внешний embedding API  
- Не внедряем Qdrant / Neo4j в v1  
- Не кешируем только по тексту запроса  
- Не пишем полный чувствительный query в обычный audit log  

---

## Краткая оценка готовности текущего `knowledge/`

| Требование Second Brain | Готовность | Комментарий |
|-------------------------|------------|-------------|
| MD как SoT | 🟡 | Freeze есть; канон → `quantum-brain` |
| Типы документов | 🔴 | Один смешанный корпус |
| Tenant + ACL + classification | 🟡 | Схемы/тесты Phase 0; runtime ещё нет |
| Physical public/private | 🔴 | Закреплено в ADR |
| Entity graph | 🔴 | Postgres v1 в плане |
| Semantic/Hybrid (pgvector) | 🔴 | |
| Safety / quarantine | 🟡 | Контракты Phase 0 |
| LLM-agnostic MCP | 🔴 | |
| Compat для агентов | 🟢 | Voice/text на общем API; switch заблокирован |

**Вывод:** `ava-knowledge` остаётся anti-corruption / compat слоем. Second Brain наращивается над ним с security-first Phase 0.
