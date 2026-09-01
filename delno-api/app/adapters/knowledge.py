import httpx

from app.core.config import get_settings


class KnowledgeAdapter:
    """HTTP adapter — swap URL when delno-knowledge is autonomous."""

    def search(self, query: str, limit: int = 5) -> dict:
        settings = get_settings()
        url = f"{settings.knowledge_base_url.rstrip('/')}/api/knowledge/query"
        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, json={"topic": query, "limit": limit})
                if response.status_code == 200:
                    return response.json()
        except httpx.HTTPError:
            pass
        # Fallback for dev when ava-knowledge is offline
        return {"results": [], "query": query, "source": "fallback", "message": "Knowledge service unavailable"}
