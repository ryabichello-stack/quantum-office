# Changelog

## [Unreleased]

### Added

- Onboarding for any tenant via Hermes: blank MD templates (company
  profile + telephony script), cabinet download, save script/tools in
  `tenant.settings.telephony`, inject inbound script on calls
- Hermes coach: «дай шаблон», «предложи/формализуй/сохрани сценарий»,
  «включи календарь и письмо» — без ручной настройки под одного клиента
- Setup status starts with company profile (not Telegram); Hermes
  attaches downloadable MD template; dogfood `kb_ready` seed ignored
- Hermes proactive SIP: apply+probe after vault save, Cursor task on
  Rejected, voice change (`tenant_voice_profiles`), billing notes for
  platform keys vs BYOK (`docs/DELNO_LLM_KEYS_AND_BILLING.md`)
- Host helper `deploy/apply_mango_sip_server.py` for Asterisk register

### Fixed

- Hermes: «пришли форму» / «введу логин» open SIP form (not KB dump);
  «ничего не понимаю» → step-by-step coach; cabinet chat skips RAG for
  dialogue; mic prefers server Whisper + reliable click handler
- Hermes: stop re-asking SIP form after vault save; status questions
  acknowledge saved credentials; phone setup needs DID + SIP
- Root cause: vault SIP was never written to Asterisk (placeholder
  `__MANGO_SIP_PASSWORD__`) — apply path restores registration flow
- Inbox: delete conversation + bulk cleanup of junk Hermes threads
- Public DELNO leads: restore SMTP owner notify (`lead_email`); site
  tenant must be `delno-demo` (not Quantum Labs)
- DELNO mail identity: point `MAIL_*` / `LEAD_SMTP_*` at Reg.ru
  hosting (`mail.hosting.reg.ru`, `office@dlno.ru`), not Quantum Labs
  `smtp.mail.ru`

### Changed

- Cabinet UX: one Hermes-language shell for all pages — labeled nav
  (Hermes / Диалоги / Заявки / Знания / Затраты / Настройки), shared
  `CabinetPage` chrome; home/onboarding/operator → Hermes; stubs cleaned

### Fixed
- Hermes office panel crash: setup check `detail` objects are stringified
  instead of rendered as React children

- Hermes: SIP/Mango secrets via secure form (not chat paste);
  `POST /v1/tenant/vault`, pending_credential_form in operator chat,
  CredentialFormCard in UI; pasted passwords redacted from transcript
- Hermes conversation memory: LLM gets prior turns; UI restores last
  hermes thread on reload; credential questions search KB first;
  mic falls back to server Whisper STT (`POST /v1/operator/stt`)
- Hermes: «зайди на сайт / собери знания» → `office.import_website`
  (fetch → KB + чипы следующих шагов коннекторов); источники больше
  не выглядят как мёртвые кнопки — отдельные action-chips
- Hermes UX: «настрой кабинет» → статус сетапа (не ложный note);
  карточка подтверждения видна в тёмном чате; mic click-to-toggle;
  дедуп источников; RU-ответ «Настройки обновлены»

### Added

- Cabinet costs: tokens + OpenAI USD себестоимость + client RUB per tenant;
  `/dashboard/billing`, Hermes panel, `GET /v1/admin/billing/overview` (platform),
  vendor price table in `billing.estimate_llm_vendor_usd`
- Hermes prod model: `gpt-5.4-mini` + OpenAI provider uses `max_completion_tokens` for gpt-5/o-series
- Phone → live inbox memory: `end_call` keeps thread open with summary/preview,
  syncs CallSession to Second Brain (`telephony.call`), inbox detail shows
  `call_session` + transcript; Asterisk bridge `start|end|turn`
- DELNO restore-from-git pack: `delno-office/*` brokers, compose stack, full
  `.env.example`, `deploy/restore_cloud4box.sh`, `docs/DELNO_RESTORE.md` (no secrets)
- Cloud4Box `dlno.ru` HTTPS ingress + SNI mux (see `docs/DLNO_DOMAINS.md`)
- Hermes chat attachments: photo/file attach + camera capture; OpenAI vision for
  images; text/docs excerpted into the turn (`/v1/operator/chat` `attachments`)
- Hermes UI rebuilt as ChatGPT/Cursor-style agent chat: full-height thread,
  floating composer, typing indicator, office status in a slide-over panel
- delno-web: Tailwind v4 + shadcn/ui (base-nova); Hermes uses Button, Textarea,
  Sheet, ScrollArea, Avatar, Badge, Tooltip (`postcss.config.cjs` for Next 15)
- Hermes phone UI: edge-to-edge, bottom nav dock, compact chips/composer,
  office panel as bottom sheet — denser minimal chat on ≤720px

### Fixed
- Hermes office panel crash: setup check `detail` objects are stringified
  instead of rendered as React children

- Hermes cabinet: phone/secretary setup no longer dumps KB FAQ when OpenAI is
  geo-blocked — deterministic coach replies with live DID/setup/health status
- Hermes chat UX: larger dialog thread, mic dictates into the input field (STT),
  send only on Submit; orb kept for full voice conversation
- Cloud4Box OpenAI egress: local xray HTTP CONNECT `inbound-grok-minsk` (:10808)
  via Minsk `up-vpn1`; `OPENAI_HTTP_PROXY`/`HTTPS_PROXY` for `delno-api` so Hermes
  LLM works despite direct geo-block

### Added

- DELNO Office OS (dogfood): `CallSession` / `CallJob`, tenant phone provisioning,
  telephony bridge (`/v1/telephony/*`), Hermes tools for setup/health/alerts and
  calls dial/list — Quantum Labs as first client (`+79699665899`)
- Docs: `docs/DELNO_OFFICE_OS_ARCHITECTURE.md` — Hermes supervisor (setup + health watch)
  + Frontline + workers
- Hermes cabinet UI (`/dashboard/hermes`): setup checklist, health panel, recent calls,
  push-to-talk mic + orb voice task input (STT → Hermes chat), Operator nav rebranded
- Quantum Labs dogfood seed: enable office connectors + feature flags + owner login
- Hermes deterministic intents (setup/health/calls) so cabinet works when OpenAI is
  geo-blocked from the VPS; channel `hermes` treated as cabinet
- OpenAI HTTP client supports `OPENAI_HTTP_PROXY` / `HTTPS_PROXY` and `OPENAI_BASE_URL`
  for SPB→Minsk→NL egress bridge (chat + TTS)
- Tenant billing: token wallet + RUB tariff, `/v1/tenant/billing/*`, Hermes panel +
  `billing.summary`; LLM usage charged from OpenAI token counts
- Hermes web tools: `web.search` / `web.fetch` / `web.browse` (Playwright when available)
- Channel dual-mode: bot token (existing) **or** QR/session start/confirm APIs for
  Telegram / MAX / Instagram
