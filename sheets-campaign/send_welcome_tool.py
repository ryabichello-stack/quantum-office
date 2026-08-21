"""Snippet / docs for AVA in_call tool send_welcome_email."""

SEND_WELCOME_EMAIL_TOOL = {
    "kind": "in_call_http_lookup",
    "phase": "in_call",
    "enabled": True,
    "is_global": False,
    "timeout_ms": 10000,
    "url": "http://127.0.0.1:8000/api/welcome/presentation",
    "method": "POST",
    "headers": {
        "Content-Type": "application/json",
        # X-Webhook-Token filled on deploy from mailru_post_call
    },
    "output_variables": {
        "email_queued": "queued",
        "email_ok": "ok",
        "email_message": "message",
    },
    "description": (
        "Отправить клиенту welcome-письмо с презентацией Quantum Labs (PDF) на email. "
        "Вызывай после подтверждённого email: после записи на встречу ИЛИ если клиент "
        "просил материалы без слота. Параметр attendee_email обязателен."
    ),
    "parameters": [
        {
            "name": "attendee_email",
            "type": "string",
            "description": "Email клиента (подтверждённый)",
            "required": True,
        },
        {
            "name": "summary",
            "type": "string",
            "description": "Короткий заголовок / имя в теме письма",
            "required": False,
        },
        {
            "name": "description",
            "type": "string",
            "description": "Контекст для письма",
            "required": False,
        },
        {
            "name": "meeting_start",
            "type": "string",
            "description": "Время встречи ISO или YYYY-MM-DD HH:MM",
            "required": False,
        },
        {
            "name": "telemost_join_url",
            "type": "string",
            "description": "Ссылка Телемост, если уже есть",
            "required": False,
        },
    ],
    "return_raw_json": False,
    "error_message": "Не удалось отправить письмо. Уточните email и попробуйте ещё раз.",
    "body_template": (
        '{"attendee_email": "{attendee_email}", "summary": "{summary}", '
        '"description": "{description}", "meeting_start": "{meeting_start}", '
        '"telemost_join_url": "{telemost_join_url}"}'
    ),
}
