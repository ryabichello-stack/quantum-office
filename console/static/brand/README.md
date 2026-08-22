# Quantum Panel — bot avatar (approved)

Orange orbit-Q · white `QUANTUM` · orange `PANEL` · black background.

```bash
python3 console/scripts/render-panel-bot-avatar.py
bash console/scripts/apply-panel-bot-branding.sh   # name + description + avatar via Bot API
```

Or from Console / Outreach UI: **«Применить брендинг»** (calls `POST /api/ops/telegram/apply-branding` with `include_profile_photo: true`).

**Сохранить** обновляет только имя и описание бота (`include_profile_photo: false`), аватар не трогает.
