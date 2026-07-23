# Second Brain — поэтапный roadmap (без потери данных)

Связан с: [`ADR-0001-second-brain.md`](./ADR-0001-second-brain.md)  
**Правило:** каждый этап обратим, имеет тесты и критерий «можно откатиться на legacy `:8017` keyword».

Статус: **Draft — ждём утверждения ADR**. Код платформы не пишем до Accept.

---

## Phase 0 — Заморозка и инвентаризация (1 шаг, низкий риск)

**Цель:** зафиксировать SoT «как есть».

### Работы
1. Снимок `quantum_labs.md` → `knowledge/vault/legacy/quantum_labs.v1.md` (+ sha256).
2. Снимок `index.yaml` → `vault/legacy/index.v1.yaml`.
3. `import-manifest.yaml` (скелет): список всех H2/H3 + предложенный `type` / `visibility` / целевой путь (ещё без переноса).
4. Документировать dual-path (`/root/ava` vs git) и выбрать канон на переходный период.

### Тесты / проверки
- diff sha256 legacy == prod MD  
- `POST :8017/query` smoke без изменений поведения  

### Rollback
- ничего не меняли в runtime → N/A  

### Exit criteria
- [ ] Манифест покрывает 100% секций монолита  
- [ ] ADR Accepted  

---

## Phase 1 — Vault skeleton + frontmatter schema (обратимо)

**Цель:** структура папок и схема метаданных **без** смены поискового движка.

### Работы
1. Создать дерево `vault/` (`products/`, `meetings/`, …) + `_meta/taxonomy.yaml`, `acl-roles.yaml`.
2. JSON Schema / pydantic-модель frontmatter (`visibility` required).
3. Скрипт `validate_vault.py` (CI): все `.md` в vault имеют валидный frontmatter.
4. Compat: runtime `:8017` **пока** продолжает читать legacy MD.

### Не делаем
- embeddings, graph DB, нарезку всех файлов  

### Exit criteria
- [ ] CI валидирует schema  
- [ ] Legacy query e2e зелёный  

---

## Phase 2 — Миграция контента (шардинг без удаления)

**Цель:** разрезать монолит на документы **копированием**.

### Стратегия нарезки
| Источник (пример) | Цель | visibility (черновик) |
|--------------------|------|------------------------|
| FAQ / продукт | `products/quantum-payouts/faq/*.md` | `company` |
| Legal / «не обещать» | `products/quantum-payouts/legal/*.md` | `team:sales` или `company` |
| AVA contacts / ops | `products/ava/ops/*.md` | `team:ops` |
| Call scripts | `products/quantum-payouts/playbooks/*.md` | `team:sales` |
| Неясно | `vault/legacy/unsorted/*.md` | `restricted` |

Каждый шард: frontmatter + `source: legacy/...#anchor`.  
Монолит остаётся в `vault/legacy/`.

### Работы
1. Авто-сплит по H2/H3 + ручной review манифеста.  
2. Feature flag `KNOWLEDGE_READ_MODE=legacy|vault|dual`.  
3. В `dual`: query склеивает результаты; приоритет vault при равной релевантности.

### Тесты
- Число символов vault shards + legacy ≥ legacy (нет потерь)  
- Spot-check: «комиссия», «СБП», «НПД» возвращают ≥ качество legacy  
- Contract: voice/mailer proxy response shape  

### Rollback
- `KNOWLEDGE_READ_MODE=legacy`  

### Exit criteria
- [ ] dual mode стабилен на проде ≥ N дней  
- [ ] unsorted < порога (например 5%)  

---

## Phase 3 — Permission Service + ACL в поиске

**Цель:** visibility начинает **реально** фильтровать.

### Работы
1. `PermissionService`: principal (agent/user/role) → набор visibility.  
2. Маппинг: voice office → `{public, company}`; owner secretary → шире; guest web → `{public}` (+опционально company FAQ).  
3. Индексы/поиск принимают `allowed_visibilities`; **filter before LLM**.  
4. Audit log table/file.  
5. Negative tests: `secret` doc никогда не попадает в guest retrieve.

### Exit criteria
- [ ] Набор ACL e2e тестов красный→зелёный  
- [ ] Compat API использует explicit principal (не «весь корпус»)  

---

## Phase 4 — Indexer pipeline + смысловой chunking

**Цель:** автоматическое обновление производных индексов из Vault.

### Pipeline
```
MD change → Normalize → Chunk(by type) → Metadata →
  EntityExtract(candidates) → Embed → Upsert Vector → Upsert Graph → Ready
```

### Работы
1. Chunkers: markdown-H2/H3, FAQ Q/A, meeting sections.  
2. Job runner (сначала sync CLI `kb index`, потом watcher).  
3. Content hash / version на документ → инкрементальный reindex.

### Exit criteria
- [ ] `kb index` идемпотентен  
- [ ] Изменение одного MD обновляет только его chunks  

---

## Phase 5 — Vector abstraction + Hybrid search

**Цель:** semantic + hybrid без привязки к одному вендору.

### Работы
1. Interface `VectorStore` + реализации: **pgvector** (предпочтительно v1, один Postgres) и/или **Qdrant**.  
2. Embedding provider pluggable (OpenAI / local) — конфиг, не хардкод.  
3. Search modes: `keyword | semantic | hybrid`.  
4. Hybrid = RRF(keyword, semantic) ± graph boost (если Phase 6 готов).

### Решение на утверждении ADR
- Default v1 backend: ___________  

### Exit criteria
- [ ] Смена backend = конфиг, без правки агентов  
- [ ] Hybrid ≥ keyword на наборе регрессионных запросов  

---

## Phase 6 — Entity Graph + Timeline

**Цель:** связи между компаниями, продуктами, встречами, ADR.

### Работы
1. Таблицы/стор: entities, edges.  
2. Extractor: frontmatter entities + LLM propose (review queue для restricted/secret).  
3. API: `related(id)`, timeline по project.  
4. Авто-обновление при index.

### Exit criteria
- [ ] Демо-граф: Quantum Payouts → банк → номинальный счёт → meeting  
- [ ] Guest не видит edges на secret nodes  

---

## Phase 7 — RAG Service + MCP Gateway (LLM-agnostic)

**Цель:** единая корпоративная память для всех AI-инструментов.

### Работы
1. `RAG.retrieve(query, principal, token_budget)` → только allowed chunks.  
2. MCP server: `kb.search`, `kb.get`, `kb.related`, `kb.upsert` (ACL write).  
3. OpenAPI стабилизирован; SDK не обязателен.  
4. Подключить text-bot и (опционально) voice tool URL к новому RAG, сохранив compat path.

### Exit criteria
- [ ] Cursor / внешний агент успешно ищут через MCP с ACL  
- [ ] Один и тот же ответный контракт для всех LLM  

---

## Phase 8 — Admin UI + операционка

**Цель:** люди могут править Vault без git-only (git остаётся SoT через sync).

### Работы
- Browse / filter by visibility  
- Reindex button  
- Review entity proposals  
- Diff legacy vs vault  

---

## Рекомендуемый порядок утверждения (чекбокс для владельца)

1. [ ] Accept ADR-0001  
2. [ ] Vault живёт в `quantum-office/knowledge/vault` (да/нет → отдельный repo)  
3. [ ] Vector v1: pgvector / Qdrant / defer  
4. [ ] Graph v1: Postgres / Neo4j / defer  
5. [ ] Default principal policies для voice / text-owner / text-guest  
6. [ ] Стартовать Phase 0  

---

## Что сознательно не делаем «сразу»

- Не удаляем `quantum_labs.md` и не выключаем keyword `:8017`  
- Не включаем `WEBHOOK_TOKEN` на knowledge без обновления mailer proxy  
- Не тащим secret/legal в `public`  
- Не строим отдельную KB «только для Cursor»  

---

## Краткая оценка готовности текущего `knowledge/` как фундамента

| Требование Second Brain | Готовность | Комментарий |
|-------------------------|------------|-------------|
| MD как SoT | 🟡 | Файл есть, но dual-path и нет frontmatter |
| Типы документов | 🔴 | Один смешанный корпус |
| Visibility/ACL | 🔴 | Нет |
| Entity graph | 🔴 | Нет |
| Semantic/Hybrid | 🔴 | Только keyword |
| Indexer pipeline | 🔴 | Только `/reload` |
| LLM-agnostic MCP | 🔴 | Только REST + OpenAI tools |
| Compat для агентов | 🟢 | Voice/text уже на общем API |
| Миграция без потери | 🟢 | Реалистична через legacy/ + manifest |

**Вывод:** текущий `ava-knowledge` — правильный **совместимый фундамент и anti-corruption layer**. Second Brain нужно наращивать **над ним** (Vault + indexes + ACL + MCP), а не выкидывать и писать с нуля.
