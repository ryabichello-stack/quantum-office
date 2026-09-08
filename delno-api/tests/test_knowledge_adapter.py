from unittest.mock import MagicMock, patch

import httpx

from app.adapters.knowledge import KnowledgeAdapter
from app.core.principals import PRINCIPAL_TEXT_GUEST, PRINCIPAL_TEXT_OWNER


def test_knowledge_adapter_sends_principal_headers():
    adapter = KnowledgeAdapter()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "ok": True,
        "matches": [
            {
                "document_id": "doc-1",
                "chunk_id": "c1",
                "title": "Demo",
                "snippet": "hello",
            }
        ],
        "denied": False,
    }

    with patch.object(httpx.Client, "__enter__", return_value=MagicMock()) as mock_ctx:
        client = mock_ctx.return_value
        client.post.return_value = mock_response
        with patch("app.adapters.knowledge.get_settings") as mock_settings:
            mock_settings.return_value.knowledge_base_url = "http://knowledge:8021"
            mock_settings.return_value.knowledge_use_legacy_principals = True
            result = adapter.search(
                "test query",
                tenant_slug="acme",
                principal_id=PRINCIPAL_TEXT_OWNER,
            )
            client.post.assert_called_once()
            _url, kwargs = client.post.call_args
            assert kwargs["headers"]["X-Tenant-Id"] == "acme"
            assert kwargs["headers"]["X-Principal-Id"] == "service:text-owner"
            assert len(result["sources"]) == 1
            assert result["sources"][0]["document_id"] == "doc-1"


def test_knowledge_adapter_isolated_when_url_empty():
    adapter = KnowledgeAdapter()
    with patch("app.adapters.knowledge.get_settings") as mock_settings:
        mock_settings.return_value.knowledge_base_url = ""
        result = adapter.search("q", tenant_slug="x", principal_id=PRINCIPAL_TEXT_GUEST)
        assert result["source"] == "isolated"
        assert result["results"] == []
