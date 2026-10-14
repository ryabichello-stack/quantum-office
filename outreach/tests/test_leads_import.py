"""CSV leads import + pack segment mapping."""

from __future__ import annotations

import tempfile
from pathlib import Path

from content.packs import get_pack, list_packs
from leads_import import import_leads, parse_leads_csv, resolve_pack_id
from outbox import OutboxStore


def test_parse_ru_headers():
    csv_text = (
        "компания;сегмент;сайт;email;телефон;ЛПР;источник\n"
        "ООО Ромашка;стройка;https://ex.ru;a@ex.ru;+7900;Иван;csv\n"
    )
    rows = parse_leads_csv(csv_text)
    assert len(rows) == 1
    assert rows[0]["email"] == "a@ex.ru"
    assert rows[0]["company"] == "ООО Ромашка"
    assert rows[0]["segment"] == "стройка"
    assert rows[0]["contact_name"] == "Иван"


def test_resolve_pack_segments():
    assert resolve_pack_id("финтех") == "agents_fintech"
    assert resolve_pack_id("1С") == "agents_1c"
    assert resolve_pack_id("сельхоз") == "agri"
    assert resolve_pack_id("аренда") == "rental"
    assert resolve_pack_id(None, "construction") == "construction"


def test_new_packs_exist():
    ids = {p["id"] for p in list_packs()}
    for pid in (
        "agents_fintech",
        "agents_1c",
        "agents_accounting",
        "construction",
        "blogger_agencies",
        "agri",
        "rental",
    ):
        assert pid in ids
        pack = get_pack(pid)
        assert pack and len(pack["steps"]) == 5


def test_import_and_dedup():
    with tempfile.TemporaryDirectory() as tmp:
        store = OutboxStore(Path(tmp) / "o.db")
        store.init_db()
        csv1 = "email,company,segment\na@ex.ru,Co,стройка\n"
        r1 = import_leads(csv_text=csv1, outbox=store, queue=True)
        assert r1["ok"] and r1["imported"] == 1
        r2 = import_leads(csv_text=csv1, outbox=store, queue=True, skip_duplicates=True)
        assert r2["imported"] == 0
        assert r2["skipped"] == 1
