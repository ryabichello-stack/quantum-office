# AVA Bitrix Outreach

Isolated SMTP outreach from Bitrix24 companies. Runs on polyhub as `ava-outreach.service` (port `8012`). Does **not** depend on Asterisk / AVA phone stack.

## Admin UI

- Local: `http://127.0.0.1:8012/ui/`
- Public (nginx): `https://a.47z.ru/_ava_outreach/ui/`
- Auth: `OUTREACH_UI_TOKEN` (see `.env`, or `python main.py ui-token`)

Tabs: overview/stats, outbox queue, inbound replies, letter editor, schedule, settings.

## Safety

- `OUTREACH_ENABLED=false` by default — batch send refused until explicitly enabled (UI or `.env`).
- Daily limit ≤ 20 (editable), random delay 60–180s.
- Schedule auto-send also requires `OUTREACH_ENABLED` + time window.

## CLI

```bash
cd /opt/ava-outreach
./venv/bin/python main.py status
./venv/bin/python main.py sync
./venv/bin/python main.py dry-run 5
./venv/bin/python main.py send-batch 1
./venv/bin/python main.py ui-token
```
