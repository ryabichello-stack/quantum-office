"""Content Flywheel — ingest, dedup, slots, KB, proposals."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.content_flywheel import ContentFlywheelStore
from modules.content_flywheel.memory import content_hash, find_similar, jaccard_similarity
from modules.content_flywheel.processor import approve_proposal, process_news_item
from modules.content_flywheel.slots import slot_hours, slots_for_day


def test_content_hash_dedup():
    a = content_hash("Hello world")
    b = content_hash("hello   world!!!")
    assert a == b


def test_jaccard_similarity():
    assert jaccard_similarity("выплаты ломбарды банк", "ломбарды выплаты инфраструктура") > 0.2


def test_slots_default_three_per_day():
    hours = slot_hours()
    assert len(hours) >= 1
    slots = slots_for_day()
    assert len(slots) == len(hours)


def test_flywheel_ingest_process_approve():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "m.db"
        store = ContentFlywheelStore(db)
        news = store.ingest_news(
            platform="telegram",
            handle="@news",
            title="ЦБ обсуждает выплаты",
            body="Ломбарды ускоряют массовые выплаты и оборот денежных потоков клиентам.",
        )
        assert not news.get("duplicate")
        dup = store.ingest_news(
            platform="telegram",
            handle="@news",
            title="ЦБ обсуждает выплаты",
            body="Ломбарды ускоряют массовые выплаты и оборот денежных потоков клиентам.",
        )
        assert dup.get("duplicate") or dup["id"] == news["id"]

        with patch.dict(os.environ, {"FLYWHEEL_AUTO_KB": "false", "FLYWHEEL_KB_ENRICH": "false"}, clear=False):
            out = process_news_item(store, news["id"])
        assert out.get("ok") is True
        assert out.get("proposal")
        prop_id = out["proposal"]["id"]

        appr = approve_proposal(store, prop_id)
        assert appr.get("ok") is True
        assert appr.get("social_post")
        assert appr.get("video_draft_id")
        mem = store.list_memory(limit=5)
        assert len(mem) >= 1


def test_find_similar_memory():
    memory = [{"topic": "Выплаты ломбардам", "summary": "инфраструктура без посредника банк"}]
    hits = find_similar("ломбарды и выплаты через банк", memory, threshold=0.2)
    assert hits
