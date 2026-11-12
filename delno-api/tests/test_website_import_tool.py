"""Website import tool must report real evidence, not a vague template."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.tools.website_import_tool import OfficeImportWebsiteTool


def test_import_reply_includes_excerpt_and_doc_id():
    tool = OfficeImportWebsiteTool()
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="ql", role="tenant_owner")
    with (
        patch("app.operator.tools.website_import_tool.import_website_to_tenant") as imp,
        patch("app.operator.tools.website_import_tool.hermes_ops.office_setup_status") as setup,
    ):
        imp.return_value = {
            "ok": True,
            "kb_ok": True,
            "url": "https://quantumlabs.ru/",
            "title": "Quantum Labs | Ваш рост — наша экспертиза",
            "description": "IT-решения и инновации в Финтехе",
            "document_id": "doc-ql-website",
            "chars": 2615,
            "paragraph_count": 6,
            "headings": ["Направления", "Услуги"],
            "excerpt": "Работаем по всему Миру\nНужна консультация",
            "sample_questions": ["Чем занимается Quantum Labs?"],
            "kb": {"ok": True},
        }
        setup.return_value = {
            "next_steps": [{"id": "telephony_script", "title": "Сценарий", "hint": "надиктуйте"}],
        }
        out = tool.run(db, ctx, url="quantumlabs.ru")
    assert out.ok
    assert "doc-ql-website" in out.message
    assert "2615" in out.message or "6 абзац" in out.message
    assert "Выдержка" in out.message
    assert "Работаем по всему Миру" in out.message
    assert "Дальше предлагаю донастроить кабинет по шагам" not in out.message
