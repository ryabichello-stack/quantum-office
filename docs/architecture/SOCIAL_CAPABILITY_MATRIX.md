# Social Sources & Channels — Capability Matrix

**Дата:** 2026-08-23  
**Статус:** AS-IS факты + целевые режимы из ТЗ.  
**Правило:** нет capability → import / user-assisted / `MANUAL_TASK`, **не** browser automation.

---

## 1. Sources (поиск / identity)

| Source | Mode AS-IS | can_search_people | can_search_by_role | can_read_profile | can_resolve_company | Trust | Cost | Next adapter |
|--------|------------|-------------------|--------------------|------------------|---------------------|-------|------|--------------|
| Bitrix CRM | API | ✅ | 🟡 | ✅ | ✅ | high | low | wrap `clients` |
| DaData / registry | API | 🟡 directors | 🟡 | — | ✅ INN | high | paid | wrap `dadata` |
| Company website | none | ❌ | ❌ | ❌ | 🟡 manual | med | low | web_import / crawler later |
| Telegram | Bot API | 🟡 username | ❌ | 🟡 | ❌ | med | low | import + inbound |
| VK | none | ❌ | ❌ | ❌ | ❌ | — | — | public/import → MANUAL |
| OK | none | ❌ | ❌ | ❌ | ❌ | — | — | public/import → MANUAL |
| TenChat | none | ❌ | ❌ | ❌ | ❌ | — | — | public/import → MANUAL |
| LinkedIn | none | ❌ | ❌ | ❌ | ❌ | — | — | permitted API/import only |
| MAX | none | ❌ | ❌ | ❌ | ❌ | — | — | official when available |
| YouTube | none | ❌ | ❌ | ❌ | 🟡 channel | — | — | metadata later |
| Email domain | derived | — | — | — | 🟡 | med | free | from ContactPoint |

---

## 2. Channels (сообщения / publish)

| Channel | Inbound AS-IS | Outbound AS-IS | Default mode (ТЗ) | Notes |
|---------|---------------|----------------|-------------------|-------|
| Email | ✅ IMAP | ✅ SMTP sequences | AUTO / APPROVAL | Core outreach |
| AVA Voice | ✅ calls | ✅ dial/callback | AUTO inbound; cold MANUAL | Console + AVA |
| Telegram bot | ✅ text-bot | 🟡 notify only | AUTO inbound | Not cold DM |
| Telegram channel | ❌ | ❌ | APPROVAL then AUTO | Need admin bot |
| VK community | ❌ | ❌ | APPROVAL publish; MANUAL DM | |
| OK group | ❌ | ❌ | MANUAL DM | |
| TenChat | ❌ | ❌ | MANUAL | |
| LinkedIn | ❌ | ❌ | MANUAL | No unofficial automation |
| Forms / site | ❌ | — | AUTO capture | Slice A adjacent |
| Callback CTA | ✅ | — | AUTO | outreach `callback_cta` |
| Calendar/meet | ✅ | ✅ | APPROVAL | calendar + conference |

---

## 3. Adapter interface (целевой контракт)

```text
SocialSourceAdapter
  get_capabilities() -> SourceCapabilityMatrix
  validate_configuration() / healthcheck()
  resolve_company(query)
  search_people(query_plan)
  search_public_content(query_plan)
  get_public_profile(reference)
  normalize_candidate(payload)
  estimate_cost(query_plan)

ChannelAdapter
  get_capabilities() -> CapabilityMatrix
  send_message / publish_content / create_manual_task
  handle_webhook / sync_status / sync_metrics
```

Первая реализация registry: `platform/connectors/` или `outreach/modules/social/` — **решение на Accept R5**.

---

## 4. Unknowns requiring legal / product Accept

1. Допустимые способы сбора публичных профилей VK/OK/TenChat в РФ/юрисдикции клиента.
2. LinkedIn: только официальные партнёрские API или user-provided URL import.
3. Retention policy для `PublicActivity` excerpts.
4. Бюджет paid enrichment (DaData already) на committee coverage.
