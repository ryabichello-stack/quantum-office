"""Stage 1 accounts: Account/Person/Lead/events + inbound resolve."""

from __future__ import annotations

import tempfile
from pathlib import Path

from modules.accounts import AccountStore, LIFECYCLE


def test_upsert_account_and_lifecycle():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(Path(tmp) / "m.db")
        acc = store.upsert_account_from_company(
            {
                "bitrix_id": "100",
                "title": "Ломбард Тест",
                "inn": "7707083893",
                "city": "Москва",
                "timezone": "Europe/Moscow",
            }
        )
        assert acc["bitrix_company_id"] == "100"
        assert acc["lifecycle_status"] == "ENRICHED"
        assert acc["legal_name"] == "Ломбард Тест"
        again = store.upsert_account_from_company(
            {"bitrix_id": "100", "title": "Ломбард Тест"}
        )
        assert again["id"] == acc["id"]
        updated = store.set_lifecycle(acc["id"], "IN_SEQUENCE")
        assert updated and updated["lifecycle_status"] == "IN_SEQUENCE"
        assert "IN_SEQUENCE" in LIFECYCLE


def test_resolve_inbound_creates_person_lead_events():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(Path(tmp) / "m.db")
        store.upsert_account_from_company(
            {"bitrix_id": "42", "title": "ООО Ромашка", "inn": "1"}
        )
        out = store.resolve_inbound(
            email="ivan@romashka.ru",
            bitrix_company_id="42",
            contact_name="Иван Петров",
            company_title="ООО Ромашка",
            classification="positive_interest",
            source="email_reply",
        )
        assert out["ok"] is True
        assert out["account"]["lifecycle_status"] == "INTERESTED"
        assert out["person"]["full_name"] == "Иван Петров"
        assert out["lead"]["status"] == "INTERESTED"
        person2 = store.find_person_by_email("ivan@romashka.ru")
        assert person2 and person2["id"] == out["person"]["id"]

        ev = store.emit_event(
            event_type="message.received",
            source="test",
            channel="email",
            account_id=out["account"]["id"],
            person_id=out["person"]["id"],
            idempotency_key="message.received:mid-1",
            payload={"from_email": "ivan@romashka.ru"},
        )
        ev2 = store.emit_event(
            event_type="message.received",
            source="test",
            channel="email",
            idempotency_key="message.received:mid-1",
            payload={"dup": True},
        )
        assert ev["id"] == ev2["id"]
        events = store.list_events(event_type="message.received")
        assert len(events) == 1


def test_blacklist_on_unsubscribe():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(Path(tmp) / "m.db")
        store.upsert_account_from_company({"bitrix_id": "7", "title": "X"})
        out = store.resolve_inbound(
            email="a@b.ru",
            bitrix_company_id="7",
            classification="unsubscribe",
        )
        assert out["account"]["lifecycle_status"] == "BLACKLISTED"
        assert out["lead"]["status"] == "BLACKLISTED"


def test_suggest_next_action_rules():
    from modules.accounts import suggest_next_action, suggested_reply_draft

    assert suggest_next_action(classification="unsubscribe")["action"] == "suppress"
    assert (
        suggest_next_action(classification="positive_interest")["action"]
        == "propose_meeting"
    )
    assert suggest_next_action(classification="negative")["action"] == "close_politely"
    assert (
        suggest_next_action(lifecycle="REPLIED", classification="human_unclassified")[
            "action"
        ]
        == "operator_reply"
    )
    draft = suggested_reply_draft(
        classification="positive_interest",
        account_name="ООО Тест",
        person_name="Иван",
        next_action=suggest_next_action(classification="positive_interest"),
    )
    assert draft["approval_required"] is True
    assert "Иван" in draft["body"]
    assert draft["citations"]


def test_enrichment_context_read_and_create():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(Path(tmp) / "m.db")
        store.upsert_account_from_company(
            {"bitrix_id": "99", "title": "Enrich Co"}
        )
        empty = store.enrichment_context(
            email="nobody@x.ru",
            bitrix_company_id="99",
            classification="human_unclassified",
        )
        assert empty["ok"] is True
        assert empty["account"]["bitrix_company_id"] == "99"
        assert empty["person"] is None
        assert empty["next_action"]["action"] == "operator_reply"

        created = store.enrichment_context(
            email="ann@enrich.ru",
            bitrix_company_id="99",
            classification="positive_interest",
            contact_name="Анна",
            create_if_missing=True,
        )
        assert created["person"]["full_name"] == "Анна"
        assert created["lead"]["status"] == "INTERESTED"
        assert created["next_action"]["action"] == "propose_meeting"
        assert created["suggested_reply"]["approval_required"] is True

        again = store.enrichment_context(
            email="ann@enrich.ru", bitrix_company_id="99"
        )
        assert again["person"]["id"] == created["person"]["id"]
        assert again["lead"]["id"] == created["lead"]["id"]
