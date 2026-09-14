# Quantum Labs Control Console

Операционный **пульт** управления секретарём Quantum Labs: автолиния входящих, робот, outreach, звонки, сценарии.

Публичный URL: https://a.47z.ru/_quantum_console/

## Что умеет

- **Пульт (Обзор):** вкл/выкл автолинии входящих (AstDB `quantum/inbound_line`), статус робота (AI + SIP + линия), glance outreach и Sheets-кампании, последние звонки
- Статус office-сервисов: mailer / knowledge / calendar / conference / files / text-bot / outreach / sheets
- Редактор сценария: greeting, prompt, model, voice, tools (`ai-agent.local.yaml`)
- База знаний `quantum_labs.md`
- История звонков и расшифровки (`call_history.db`)
- Исходящий тестовый звонок + обзвон Google Sheets
- Встроенный Outreach UI (прокси с токеном)
- Чеклист секретов, бэкап, inventory пакета

## Автолиния

Dialplan `from-mango` читает AstDB:

| значение | поведение |
|----------|-----------|
| `on` или ключ отсутствует | принять → Stasis / ИИ |
| `off` | Busy, без OpenAI |

API:

```http
GET  /api/line
POST /api/line  {"enabled": true|false}
```

## Prod deploy

```bash
rsync -a --delete --exclude venv --exclude .env --exclude '__pycache__' \
  console/ root@HOST:/tmp/quantum-console-src/
ssh root@HOST 'bash /tmp/quantum-console-src/scripts/install_prod.sh'
```

Локально на сервере: `http://127.0.0.1:8013/` (nginx → `/_quantum_console/`).

Токен: `grep CONSOLE_TOKEN /opt/quantum-console/.env`

## Пути на проде

| git | prod |
|-----|------|
| `console/` | `/opt/quantum-console` |
| `console/asterisk/extensions.quantum-labs.conf` | `/root/ava/config/asterisk/` + `/etc/asterisk/extensions.conf` |
