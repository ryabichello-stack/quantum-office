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
