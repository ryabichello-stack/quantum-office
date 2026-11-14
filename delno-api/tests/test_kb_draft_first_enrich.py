"""Draft First: show draft, save/enrich/edit trio, enrich ≠ confirm."""

from __future__ import annotations

from app.api.v1.operator import _wants_confirm_kb_draft, _wants_enrich_kb_draft
from app.services.hermes_guide import (
    format_kb_draft_owner_reply,
    kb_draft_cta_footer,
    kb_draft_next_actions,
    prefer_pending_kb_draft_reply,
)


def test_enrich_intent_is_not_confirm():
    assert _wants_enrich_kb_draft("обогати базу")
    assert _wants_enrich_kb_draft("Обогати черновик через интернет-поиск")
    assert _wants_enrich_kb_draft("дособери из внешних данных")
    assert not _wants_confirm_kb_draft("обогати базу")
    assert not _wants_confirm_kb_draft("обогати базу из внешних данных")
    assert _wants_confirm_kb_draft("положи в кб")
    assert _wants_confirm_kb_draft("подтверди черновик")


def test_kb_draft_next_actions_trio():
    chips = kb_draft_next_actions()
    titles = [c["title"] for c in chips]
    assert titles == ["Сохранить в KB", "Обогатить поиском", "Доработать"]
    assert "обогати" in chips[1]["text"].lower()
    assert "подтверди" in chips[0]["text"].lower()


def test_cta_footer_recommends_enrich_when_gaps():
    text = kb_draft_cta_footer(gaps=["цены", "соцсети"])
    assert "черновик" in text.lower()
    assert "Сохранить" in text
    assert "Обогатить" in text
    assert "Доработать" in text
    assert "цены" in text


def test_prefer_pending_replaces_thin_nous_status():
    class _FakeDb:
        pass

    class _FakeCtx:
        tenant_id = None
        tenant_slug = "t"

    draft = {
        "status": "draft",
        "title": "Acme",
        "body": "## 1. Кто мы\nAcme Corp делает выплаты\n\n## 2. Продукты\nAPI и СБП\n" * 5,
    }
    tools = [
        {
            "tool": "office.build_kb_draft",
            "ok": True,
            "full_message": "Собрал\n\n" + draft["body"] + "\n" + kb_draft_cta_footer(),
        }
    ]
    # Monkeypatch get_office_loop via tool full_message path (no db needed).
    out = prefer_pending_kb_draft_reply(
        _FakeDb(),  # type: ignore[arg-type]
        _FakeCtx(),  # type: ignore[arg-type]
        "Черновик KB уже собран. Добавить в KB?",
        tool_calls=tools,
    )
    assert "## 1. Кто мы" in out
    assert "Обогатить" in out or "обогати" in out.lower()


def test_format_kb_draft_owner_reply_includes_status():
    text = format_kb_draft_owner_reply(
        {"title": "QL", "body": "## Услуги\nВыплаты"},
        gaps=["Telegram"],
    )
    assert "## Услуги" in text
    assert "ещё не сохранён" in text.lower() or "не сохранён" in text.lower()
    assert "Telegram" in text
