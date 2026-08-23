"""Content Studio + Intent Radar MVP."""

from __future__ import annotations

import tempfile
from pathlib import Path

from modules.content_studio import ContentStudioStore
from modules.radar import RadarStore


def test_content_draft_from_objection():
    with tempfile.TemporaryDirectory() as tmp:
        store = ContentStudioStore(Path(tmp) / "m.db")
        draft = store.draft_from_objection(
            objection="Дорого / уже есть банк",
            industry_pack="lombards",
        )
        assert draft["status"] == "draft"
        assert draft["body"]["approval_required"] is True
        assert draft["body"]["letters"]
        approved = store.set_status(draft["id"], "approved")
        assert approved and approved["status"] == "approved"
        assert approved.get("approved_at")


def test_radar_signal_no_auto_outreach():
    with tempfile.TemporaryDirectory() as tmp:
        store = RadarStore(Path(tmp) / "m.db")
        sig = store.ingest(
            signal_type="hiring_payments",
            summary="Ломбард ищет интегратора выплат",
            company_title="Тест Ломбард",
            score=0.85,
        )
        out = store.verify_and_suggest_action(sig["id"])
        assert out["auto_outreach"] is False
        assert out["approval_required"] is True
        assert out["suggested_action"] == "run_lpr_search"
