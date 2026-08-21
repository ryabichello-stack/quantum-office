---
tenant_id: quantum-labs
visibility: company
classification:
  level: internal
  contains_personal_data: false
channels: [office-assistant]
ai_processing:
  allow_external_embed: true
publication:
  manual_approve: false
source: imported:/opt/ava-outreach/docs/ARCHITECTURE.md
shard: outreach-architecture
---

# AVA Outreach — architecture

> Imported from `/opt/ava-outreach/docs/ARCHITECTURE.md` for Second Brain. Secrets must not be added here.

# Outreach architecture (modular)

Goal: add features without coupling to telephony (Asterisk/AVA) or polyhub trading.

## Layout

```
extras/quantum-outreach/
  main.py                 # thin app + CLI; wires modules
  core/
    registry.py           # ModuleRegistry / AppContext
    paths.py              # DATA_DIR, modules.db
  modules/
    tracking/             # Message-ID chains + optional plus Reply-To
    deliverability/       # warmup, domain cap, suppression
  outbox.py / sender.py / …   # existing domain services (stable APIs)
  static/                 # admin UI
```

## Adding a module

1. Create `modules/<name>/__init__.py` with a class implementing:
   - `name`, `version`
   - `init_db()`, `on_startup(ctx)`, `on_shutdown()`, `health()`, `register_routes(router)`
2. Register in `main.py`: `_registry.register(MyModule())`
3. Own tables live in `data/modules.db` (or a dedicated file) — do **not** alter unrelated schemas casually.
4. Expose UI only via `/api/modules/<name>/…` (token-auth).

## Anti-ban / deliverability

| Control | Default | Notes |
|--------|---------|-------|
| Stable From | `office@` | Never rotate From; reputation lives there |
| Message-ID | always | Primary reply chain key |
| Plus Reply-To | off | `office+au.<id>.<sig>@domain` — enable after Mail.ru smoke |
| Warm-up | on | Effective daily cap ramps 5→30 |
| Domain cap | 2/day | Max sends per recipient domain |
| Delay jitter | 60–180s | Between messages |
| Suppression | empty | unsub / bounce / manual |
| Send window | optional | Schedule module |

### Plus addresses (Mail.ru)

- Correct: `office+au.42.ab12cd34@quantumlabs.ru`
- Wrong: `au1+office@quantumlabs.ru` (mailbox would be `au1`)
- Mail.ru Business **may not** deliver plus aliases to the base inbox. We keep Message-ID as source of truth; plus is optional secondary signal (`TRACKING_PLUS_REPLY_TO`).

## Isolation

- Systemd unit `ava-outreach` only — no deps on asterisk / mango / AVA docker.
- Nginx path `/_ava_outreach/` proxies to `127.0.0.1:8012`.
