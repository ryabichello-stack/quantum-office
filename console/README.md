# Console — Quantum Labs telephony ops UI

Prod: `/opt/quantum-console` · `https://a.47z.ru/_quantum_console/` · port `8013`

## Calls / transcripts

Tab **Звонки** is the source of truth for **outbound** results:

- Filter defaults to `outbound`
- Table columns: time, context, phone, duration, outcome, message preview
- Click a row → full turn table (who / message)

Inbound still gets «Новый лид» email via mailer post-call. Outbound does **not**
(`contexts.outbound.post_call_tools: []`, and mailer skips outbound payloads).

## Deploy

```bash
# from repo
cp main.py static/* /opt/quantum-console/...
systemctl restart quantum-console
```
