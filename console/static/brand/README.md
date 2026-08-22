# Quantum Panel — bot identity

Premium Telegram identity for **@Quantum_panel_bot**.

## Files

| File | Use |
|------|-----|
| `quantum-panel-bot-icon.svg` | **Avatar** — symbol only (Apple-style: no text on icon) |
| `quantum-panel-bot-512.png` | Rendered avatar (512×512) |
| `quantum-panel-bot.svg` | Full lockup with QUANTUM / PANEL wordmark |
| `quantum-panel-bot-lockup-512.png` | Rendered lockup for previews / docs |

## Design principles

- Dark graphite gradient (`#1c1c1e` → `#000`) — Apple system dark
- Single accent arc + control bar — quantum orbit + operator panel
- Typography: SF Pro–style, wide tracking, light + semibold pair
- **Telegram shows bot name separately** — icon stays readable at 64px

## Apply

```bash
BOT_TOKEN=... ./scripts/apply-panel-bot-branding.sh
```

Avatar: @BotFather → `/setuserpic` → upload `quantum-panel-bot-512.png`.
