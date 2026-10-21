"""Mini-CRM account upsert / lifecycle."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from modules.accounts import AccountStore, LIFECYCLE
from modules.clients import ClientsStore


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
    assert acc["primary_phone"] == "79990001122"
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


def test_list_accounts_cyrillic_search(tmp_path: Path) -> None:
    store = AccountStore(db_path=tmp_path / "modules.db")
    store.upsert_manual(name='ООО "Центральный ломбард"', create_lead=False, source="test")
    found = store.list_accounts(q="центральный", limit=10)
    assert any("Центральный" in a["legal_name"] for a in found)


def test_additional_phones_on_card_no_dupe_contact_lead(tmp_path: Path) -> None:
    """Extra numbers beyond registry land on company card; re-enrich is idempotent."""
    store = AccountStore(db_path=tmp_path / "modules.db")
    first = store.upsert_manual(
        name="Центральный ломбард",
        phone="74951234567",  # registry / primary on create
        contact_name="Петров Пётр",
        lifecycle_status="ENRICHED",
        source="test",
    )
    aid = first["account"]["id"]
    person_id = first["person"]["id"]
    lead_id = first["lead"]["id"]
    assert first["account"]["primary_phone"] == "74951234567"
    assert first["account"]["additional_phones"] == []

    # Enrich: found reception number — must NOT replace primary, NOT new person/lead
    second = store.upsert_manual(
        name="Центральный ломбард",
        phone="79001112233",  # legacy MCP: lone phone on existing = additional
        contact_name="Петров Пётр",
        lifecycle_status="ENRICHED",
        source="test",
    )
    assert second["created"] is False
    acc = second["account"]
    assert acc["id"] == aid
    assert acc["primary_phone"] == "74951234567"
    assert "79001112233" in acc["additional_phones"]
    assert second["person"]["id"] == person_id
    assert second["lead"]["id"] == lead_id

    third = store.upsert_manual(
        name="Центральный ломбард",
        additional_phones=["79001112233", "79005556677"],
        create_lead=False,
        source="test",
    )
    assert third["lead"] is None
    assert set(third["account"]["additional_phones"]) >= {"79001112233", "79005556677"}
    assert third["account"]["primary_phone"] == "74951234567"
    assert len(store.list_people_for_account(aid)) == 1
    assert len(store.list_leads_for_account(aid)) == 1

    # Simulate prior spam: force a second person+lead, then dedupe
    spam = store.ensure_person(
        full_name="Центральный ломбард", account_id=aid, title=""
    )
    store.upsert_lead(
        account_id=aid, person_id=spam["id"], source="test-spam", status="NEW"
    )
    cleaned = store.dedupe_account_people_leads(aid)
    assert cleaned["ok"] is True
    assert cleaned["removed_people"] >= 1
    assert len(cleaned["people"]) == 1
    assert cleaned["people"][0]["id"] == person_id


def test_sync_from_clients_new_skips_existing(tmp_path: Path) -> None:
    """Full Bitrix mirror → accounts: NEW for missing, no dupe of ENRICHED."""
    clients = ClientsStore(db_path=tmp_path / "clients.db")
    with clients.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
        for col, decl in (
            ("director_name", "TEXT"),
            ("timezone", "TEXT"),
            ("city", "TEXT"),
            ("region", "TEXT"),
        ):
            if col not in cols:
                conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {decl}")
        for bid, title in (("10", "Already"), ("20", "Fresh A"), ("30", "Fresh B")):
            conn.execute(
                """
                INSERT INTO companies(
                    bitrix_id, title, emails_json, phones_json, synced_at, updated_at,
                    inn, director_name, timezone
                ) VALUES (?, ?, '[]', '[]', datetime('now'), datetime('now'),
                          '7707083893', 'Иванов Иван', 'Europe/Moscow')
                """,
                (bid, title),
            )

    store = AccountStore(db_path=tmp_path / "modules.db")
    existing = store.upsert_account_from_company(
        {
            "bitrix_id": "10",
            "title": "Already",
            "inn": "7707083893",
            "director_name": "Иванов",
            "timezone": "Europe/Moscow",
        }
    )
    assert existing["lifecycle_status"] == "ENRICHED"

    with patch("modules.clients.ClientsStore", return_value=clients):
        # AccountStore.sync_from_clients imports ClientsStore inside the method
        out = store.sync_from_clients(limit=100, lifecycle_for_new="NEW")

    assert out["ok"] is True
    assert out["created"] == 2
    assert out["skipped"] == 1
    assert out["scanned"] == 3

    by10 = store.get_account_by_bitrix("10")
    assert by10 and by10["id"] == existing["id"]
    assert by10["lifecycle_status"] == "ENRICHED"

    for bid in ("20", "30"):
        acc = store.get_account_by_bitrix(bid)
        assert acc is not None
        assert acc["lifecycle_status"] == "NEW"

    # second pass: nothing new
    with patch("modules.clients.ClientsStore", return_value=clients):
        again = store.sync_from_clients(limit=100)
    assert again["created"] == 0
    assert again["skipped"] == 3
