# AVA voice tools cutover (calendar :8014, conference :8016)

Applied on prod `ai-agent.local.yaml` (backup beside the file).

## Voice in-call tools

| Tool | URL |
|------|-----|
| check_calendar | `POST http://127.0.0.1:8014/api/calendar/check` |
| create_calendar_event | `POST http://127.0.0.1:8014/api/calendar/create` |
| create_conference | `POST http://127.0.0.1:8016/api/conferences` |
| send_welcome_email | `POST http://127.0.0.1:8000/api/welcome/presentation` |
| get_company_knowledge | `POST http://127.0.0.1:8000/api/knowledge/query` (unchanged) |

All calendar/conference calls need header `X-Webhook-Token` (same secret as `mailru_post_call`).

`create_calendar_event` sets `create_telemost: true` → calendar calls conference `:8016`.  
Welcome PDF is queued via `POST :8000/api/welcome/presentation` from calendar after create.

## Apply / reload

After YAML edit:

```bash
cd /root/ava && docker compose restart ai_engine
curl -sS http://127.0.0.1:15000/health
```

`POST /reload` alone does **not** re-register in-call HTTP tool URLs.

Do not restart Asterisk / Polyhub / Mango / VPN for this change.
