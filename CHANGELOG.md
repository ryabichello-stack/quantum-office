# Changelog

## [Unreleased]

### Added

- Hermes chat attachments: photo/file attach + camera capture; OpenAI vision for
  images; text/docs excerpted into the turn (`/v1/operator/chat` `attachments`)
- Hermes UI rebuilt as ChatGPT/Cursor-style agent chat: full-height thread,
  floating composer, typing indicator, office status in a slide-over panel

### Fixed

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
