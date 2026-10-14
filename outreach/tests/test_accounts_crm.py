"""Mini-CRM account upsert / lifecycle."""

from __future__ import annotations

from pathlib import Path

from modules.accounts import AccountStore, LIFECYCLE


def test_upsert_and_lifecycle(tmp_path: Path) -> None:
    store = AccountStore(db_path=tmp_path / "modules.db")
    out = store.upsert_manual(
        name="ООО Тест CRM",
        email="lpr@test-crm.example",
        phone="+79990001122",
        lifecycle_status="NEW",
        contact_name="Иван",
        note="первый контакт",
        source="test",
    )
    assert out["created"] is True
    acc = out["account"]
    assert acc["legal_name"] == "ООО Тест CRM"
    assert acc["lifecycle_status"] in LIFECYCLE
    aid = acc["id"]

    again = store.upsert_manual(
        name="ООО Тест CRM",
        email="lpr@test-crm.example",
        lifecycle_status="INTERESTED",
        note="ответил",
    )
    assert again["created"] is False
    assert again["account"]["id"] == aid
    assert again["account"]["lifecycle_status"] == "INTERESTED"

    moved = store.set_lifecycle(aid, "MEETING_BOOKED")
    assert moved and moved["lifecycle_status"] == "MEETING_BOOKED"

    listed = store.list_accounts(lifecycle="MEETING_BOOKED", limit=10)
    assert any(a["id"] == aid for a in listed)
    funnel = store.funnel_counts()
    assert funnel["MEETING_BOOKED"] >= 1
