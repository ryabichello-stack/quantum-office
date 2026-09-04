# DELNO — аудит: Crystal Widget + Conversation Core

**Revision:** AUDIT-1.0 · **2026-09-04**  
**Ветка:** `cursor/delno-api-scaffold-14e9`  
**Связано:** [`DELNO_FOR_CHATGPT.md`](DELNO_FOR_CHATGPT.md) REV-4.1 · [`DELNO_IMPLEMENTATION_ROADMAP.md`](DELNO_IMPLEMENTATION_ROADMAP.md)

**Продуктовый принцип:** один DELNO · одна память · один разговор · разные каналы.

---

## 1. Цель этапа

Собрать продуктовый цикл без новых больших подсистем:

```
посетитель → Crystal Widget → ответ по KB → имя/контакт → лид → inbox → голос → каналы
```

Не строить: второй Conversation Core, второй Operator, второй widget backend, отдельную voice memory.

---

## 2. Executive summary

| Область | Статус | Комментарий |
|---------|--------|-------------|
| Conversation Core (PG) | ✅ | `conversations` + `messages` — единая session |
| Public Widget API | ✅ | `POST /v1/public/widget/{session,visitor,message}` |
| Operator reuse | ✅ | `run_operator_turn(channel="widget")` — не `/operator/chat` из browser |
| Lead capture E3.8 | ✅ | `widget_flow.py` → `create_lead_record` |
| Crystal UI (React, dlno.ru) | ✅ | `DELNO-site-v23/components/widget/` |
| CDN embed bundle | 🔄 | `delno-widget/` — iframe, voice mock, assets missing |
| Text chat end-to-end (CDN) | 🔄 | логика есть в `index.html`, embed page не production-ready |
| Voice WebRTC E3.5 | ⬜ | |
| Voice→text fallback E3.6 | ⬜ | |
| Telegram auto-reply E2.2 | 🔄 | inbound only |
| Security (rate limit, session bind) | ⬜ | |
| Instant Demo / Website-to-Agent | ⬜ | P4 |

**Вывод:** backend Conversation Core готов; основная работа — **CDN Crystal Widget UI + hardening**, затем voice и Telegram reply через тот же core.

---

## 3. Что уже существует (переиспользовать)

### Backend (`delno-api`)

| Компонент | Путь | Роль |
|-----------|------|------|
| Conversation / Message | `app/models/conversation.py` | Unified session = `conversation.id` |
| Public widget gateway | `app/api/v1/public.py` | Tenant via `site_key`, не tenant_id из browser |
| Widget flow | `app/services/widget_flow.py` | Session, name/phone funnel, lead |
| Operator turn | `app/operator/agent.py` | `run_operator_turn` — text + voice modality |
| Channel router | `app/services/channel_router.py` | `resolve_widget(public_key)` |
| Inbox presentation | `app/services/conversation_present.py` | Все каналы в cabinet |
| Telegram inbound | `app/services/inbound_messages.py` | PG only, no reply |
| Events | `app/services/events.py` | `widget.*`, `message.received` |

### Frontend

| Компонент | Путь | Роль |
|-----------|------|------|
| Crystal Widget (canonical UI) | `DELNO-site-v23/components/widget/` | Orb + chat panel + voice hook |
| Crystal CSS | `DELNO-site-v23/components/widget/crystal-widget.css` | Phase-driven orb animations |
| Site proxy | `DELNO-site-v23/app/api/widget/message/route.ts` | Browser → delno-api |
| CDN loader | `delno-widget/embed.js` | Script tag → iframe |
| CDN client | `delno-widget/delno-widget-client.js` | `/public/widget/*` only |
| Cabinet orb | `delno-web/components/CrystalOrb.tsx` | Operator stage (не embed) |

### Public API (реализовано)

```
POST /v1/public/widget/session   → conversation UUID (= session_id)
POST /v1/public/widget/visitor   → name/phone → lead
POST /v1/public/widget/message   → run_operator_turn → reply + next_step
```

Browser **не** вызывает `/v1/operator/chat`.

---

## 4. Архитектура (целевая)

```
Widget (CDN / dlno.ru)
        ↓
Public Widget API  (/v1/public/widget/*)
        ↓
site_key → resolve_widget → tenant_id + guest principal
        ↓
Conversation (id = session_id)
        ↓
run_operator_turn(channel=widget|telegram)
        ↓
Knowledge (tenant-scoped, guest ACL)
        ↓
Message rows + events
        ↓
Lead (optional) → Inbox
```

Каналы разные; conversation logic одна.

---

## 5. Unified session (text + voice)

**Уже так в модели:**

- `session_id` widget = `conversations.id`
- `messages.meta.modality` = `"text"` | `"voice"`
- `run_operator_turn(..., input_modality=...)` — один turn path

**Gap:** CDN bundle не шлёт voice transcript через `/message`; React widget на dlno.ru — ближе к цели.

---

## 6. Lead capture (E3.8)

```
visitor → conversation → name → phone → lead (once)
```

- `widget_next_step`: `ask_name` → `ask_phone` → done
- `apply_widget_visitor` + `create_lead_record(source="widget")`
- Name after first substantive answer (≥8 chars) — client + server
- Anonymous conversation без phone — OK

---

## 7. Что отсутствует / gaps

### P1 — Text product loop

- [ ] Production embed page (`widget-embed.html`) без demo landing
- [ ] External `crystal-widget.css` в CDN bundle
- [ ] Orb asset в repo/CDN
- [ ] `embed.js` — компактный iframe / inline mount
- [ ] Убрать mockAnswer при backend failure → user-friendly error
- [ ] `ensureSession` перед первым message (client)

### P2 — Security

- [ ] Rate limit `(site_key, IP)`
- [ ] Bind `visitor_id` to session
- [ ] CORS fix (`allow_credentials` + `*`)
- [ ] Integration tests (cross-tenant, invalid site_key)

### P3 — Voice + channels

- [ ] E3.5 WebRTC / Realtime voice, same session
- [ ] E3.6 voice fail → open text, same session
- [ ] E2.2 Telegram: webhook → operator → send_reply
- [ ] Runtime voice phases → orb UI (не CSS timer)

### P4 — Product-led growth

- [ ] «Создать сотрудника по моему сайту» (Instant Demo)
- [ ] Operator onboarding assistant
- [ ] TTFV events (< 3–5 min target)

---

## 8. Риски дублирования

| Риск | Митигация |
|------|-----------|
| Второй widget backend | Использовать только `/v1/public/widget/*` ✅ |
| Отдельный voice agent | STT/TTS = transport; turn = `run_operator_turn` |
| Два Crystal UI | Source of truth: `DELNO-site-v23/components/widget/` → port в `delno-widget/` |
| Telegram agent loop | `record_inbound` + `run_operator_turn` + `send_reply` |
| Client → `/operator/chat` | Запрещено; gateway only ✅ |

---

## 9. Миграции

**Не нужны** для P1–P3:

- Schema `conversations`, `messages`, `leads.conversation_id` достаточна
- `widget_allowed_origins` — можно в `tenants.settings` JSONB
- `website_import_jobs` — только для P4 Instant Demo

---

## 10. Definition of Done (этап)

### A. Text (P1)

1. Demo/client site → bubble → question → KB answer  
2. Conversation in PG  
3. Name after value → saved  
4. Inbox shows thread  
5. Lead linked when phone given  

### B. Voice (P2)

6. Orb → listen → STT → same conversation  
7. Reply + speak phase  
8. Text chat shows voice history  

### C. Fallback (P2)

9. Mic denied → text offer, session kept  

### D. Security (P2)

10. site_key isolation, no arbitrary tenant_id, rate limit, CORS  

### E. Mobile (P1–P2)

11. Safari/Chrome smooth, panel grows up, orb performant  

---

## 11. План коммитов

| # | Scope | DoD |
|---|-------|-----|
| **1** | Crystal CDN embed + functional text chat | A.1–A.5 |
| **2** | Security: rate limit, visitor bind, CORS, tests | D.* |
| **3** | Unified session: voice transcript → `/message`, history | B.17–19 |
| **4** | E3.5 voice + E3.6 fallback | B.11–16, C.20–23 |
| **5** | E2.2 Telegram auto-reply + docs | Telegram in inbox with reply |

**P4 отдельно:** Website-to-Agent MVP.

---

## 12. Файлы для изменения (Commit 1)

| Файл | Действие |
|------|----------|
| `delno-widget/widget-embed.html` | NEW — minimal embed page |
| `delno-widget/crystal-widget.css` | COPY from site-v23 |
| `delno-widget/delno-widget-chat.js` | NEW — chat logic |
| `delno-widget/embed.js` | UPDATE — load embed page |
| `delno-widget/delno-widget-client.js` | UPDATE — session before message |
| `delno-widget/assets/` | NEW — orb SVG fallback |
| `delno-widget/INTEGRATION.md` | UPDATE — status |

**Не трогать в Commit 1:** cabinet, marketing `/`, telephony, CRM.

---

## 13. Тесты (roadmap)

| Test | Commit |
|------|--------|
| Integration session → message → DB | 2 |
| Invalid site_key, cross-tenant | 2 |
| visitor_id mismatch | 2 |
| Rate limit 429 | 2 |
| Name/lead funnel | 1–2 |
| Telegram auto-reply mock | 5 |

---

## 14. Prod / deploy notes

- CDN publish: `/opt/delno/cdn/widget/v1/` → `cdn.dlno.ru`
- Embed snippet unchanged: `embed.js` + `data-site-key`
- CORS changes — проверить `app.dlno.ru` + client origins
- Не ломать: `/opt/polyhub`, `/root/ava`, ava-outreach

---

## 15. DO NOT START

Full CRM, E1.16 Bitrix push, marketplace, PSTN/SIP, booking, fake appointment UI, billing, repo migration, landing redesign, v4 hero default.

---

## 16. Следующий шаг

**Commit 1 (in progress):** production embed page + functional text chat через existing Public Widget API.

После e2e smoke — обновить этот документ секцией «Commit 1 verified».
