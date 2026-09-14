# Changelog

## Unreleased

### Console — Telegram Mini App «Пульт»
- Mini App tabs: **Каналы** (Metrika + Tilda today), **Outreach** (send queue/limits), **Звонки** (chat dial flow + recent outbound).
- New APIs: `GET /api/miniapp/outreach`, `GET /api/miniapp/calls` (Telegram initData).
- Menu button default text: **Пульт** (`scripts/set_miniapp_menu.py`).


### Console — Telegram Mini App (today)
- Mini App at `/miniapp/`: today's Yandex Metrika + Tilda webhook leads (MSK).
- Auth via Telegram `initData` (owner allowlist) or console session.
- Menu button script: `console/scripts/set_miniapp_menu.py` → @Quantum_office_bot.

### Console — channels report
- New **Каналы** tab: Telegram / Max / email / calls / Tilda for a date range.
- Tilda forms webhook → SQLite + owner notify (Telegram/Max via text-bot).
- Yandex Metrika: counter + OAuth token setup in UI; visits/users/pageviews/bounce.
- Settings gear in the console top bar: on **Каналы** opens Tilda/Metrika setup; on **Outreach** opens campaign settings. OAuth uses a real link (no blocked popup).
- Docs: `docs/CHANNELS_REPORT.md`.
