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
| Warm-up | on | Effective daily cap ramps 3→15 (never 296/day) |
| Daily limit | 15 | `OUTREACH_DAILY_LIMIT` — hard SMTP ceiling |
| First-touch pace | auto | `POST /api/modules/sequences/pace-queue` spreads backlog via `not_before` |
| Domain cap | 2/day | Max sends per recipient domain |
| Delay jitter | 60–180s | Between messages |
| Suppression | empty | unsub / bounce / manual |
| Send window | optional | Schedule module |

**Календарь 296 на понедельник ≠ 296 писем сегодня.** Это бэклог «готовы к слоту». Уйдёт максимум `effective_daily_limit` (warmup). Кнопка **«Разложить очередь»** раскладывает первые письма по ~8/день.

### Plus addresses (Mail.ru)

- Correct: `office+au.42.ab12cd34@quantumlabs.ru`
- Wrong: `au1+office@quantumlabs.ru` (mailbox would be `au1`)
- Mail.ru Business **may not** deliver plus aliases to the base inbox. We keep Message-ID as source of truth; plus is optional secondary signal (`TRACKING_PLUS_REPLY_TO`).

## Isolation

- Systemd unit `ava-outreach` only — no deps on asterisk / mango / AVA docker.
- Nginx path `/_ava_outreach/` proxies to `127.0.0.1:8012`.
