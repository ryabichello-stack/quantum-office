# Phone → live memory (inbox + Second Brain)

## Flow

1. Asterisk / worker: `POST /v1/telephony/inbound/start` → `CallSession` + `Conversation(channel=phone)`
2. During call: `POST /v1/telephony/calls/turn` → Frontline Operator messages
3. Hangup: `POST /v1/telephony/calls/end` with `transcript` / `summary` (optional `generate_summary`, `recording_url`)
4. Result:
   - Inbox thread stays **open** (`needs_review`), preview = summary
   - System message `kind=call_summary`
   - Second Brain doc `doc-{tenant}-call-{session_id}` (`source=telephony.call`, company/private)
   - `GET /v1/operator/conversations/{id}` includes `call_session` + transcript

## Bridge

`delno-api/deploy/asterisk_delno_bridge.sh start|end|turn`

Env: `DELNO_API_BASE`, `TELEPHONY_WEBHOOK_TOKEN`.
