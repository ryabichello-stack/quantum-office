import httpx

from app.core.config import get_settings


class MessengerAdapter:
    """HTTP adapter to ava-text-bot — replaced by delno-channels later."""

    def chat(self, *, channel: str, user_id: str, message: str) -> dict:
        settings = get_settings()
        url = f"{settings.messenger_base_url.rstrip('/')}/api/chat"
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json={"channel": channel, "user_id": user_id, "message": message},
            )
            response.raise_for_status()
            return response.json()
