import httpx

from app.core.config import get_settings
from app.core.principals import brain_principal_id


class KnowledgeAdapter:
    """HTTP adapter to delno-knowledge /api/brain/search with ACL principals."""

    def search(
        self,
        query: str,
        *,
        tenant_slug: str,
        principal_id: str,
        limit: int = 5,
        mode: str = "hybrid",
    ) -> dict:
        settings = get_settings()
        base = (settings.knowledge_base_url or "").strip()
        if not base:
            return {
                "ok": False,
                "results": [],
                "matches": [],
                "query": query,
                "source": "isolated",
                "message": "Knowledge adapter disabled (KNOWLEDGE_BASE_URL empty)",
            }

        brain_pid = brain_principal_id(
            principal_id, use_legacy=settings.knowledge_use_legacy_principals
        )
        url = f"{base.rstrip('/')}/api/brain/search"
        headers = {
            "Content-Type": "application/json",
            "X-Tenant-Id": tenant_slug,
            "X-Principal-Id": brain_pid,
        }
        body = {"query": query, "limit": limit, "mode": mode}

        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(url, json=body, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    data.setdefault("source", "delno-knowledge")
                    data["principal_id"] = principal_id
                    data["brain_principal_id"] = brain_pid
                    return data
                return {
                    "ok": False,
                    "query": query,
                    "source": "delno-knowledge",
                    "message": f"Knowledge service HTTP {response.status_code}",
                    "results": [],
                    "matches": [],
                }
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "query": query,
                "source": "fallback",
                "message": f"Knowledge service unavailable: {exc}",
                "results": [],
                "matches": [],
            }
