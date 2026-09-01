import httpx

from app.core.config import get_settings
from app.models.lead import Lead


def notify_lead_telegram(lead: Lead) -> bool:
    settings = get_settings()
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    text = "\n".join(
        [
            "Новая заявка DELNO",
            f"Источник: {lead.source}",
            f"Имя: {lead.name}",
            f"Телефон: {lead.phone}",
            *( [f"Компания: {lead.company}"] if lead.company else [] ),
            *( [f"Почта: {lead.email}"] if lead.email else [] ),
            *( [f"Сайт: {lead.website}"] if lead.website else [] ),
        ]
    )
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.post(url, json={"chat_id": chat_id, "text": text})
            return response.is_success
    except httpx.HTTPError:
        return False
