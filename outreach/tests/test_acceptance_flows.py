"""Acceptance-style flows for Slice A / B / Video (unit E2E)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.accounts import AccountStore
from modules.consent import ConsentLedgerStore
from modules.replies.classify import classify_reply
from modules.sequences import SequenceStore
from modules.social import SocialStore
from modules.video_studio import VideoStudioStore
from send_guards import check_send_allowed


def test_a1_a5_inbound_resolve_and_dedupe_person():
    with tempfile.TemporaryDirectory() as tmp:
        store = AccountStore(Path(tmp) / "m.db")
        store.upsert_account_from_company({"bitrix_id": "77", "title": "Ломбард А"})
        out1 = store.resolve_inbound(
            email="ivan@a.ru",
            bitrix_company_id="77",
            contact_name="Иван",
            classification="positive_interest",
        )
        out2 = store.resolve_inbound(
            email="ivan@a.ru",
            bitrix_company_id="77",
            contact_name="Иван Петров",
            classification="human_unclassified",
        )
        assert out1["person"]["id"] == out2["person"]["id"]  # A5
        assert out1["account"]["lifecycle_status"] == "INTERESTED"
        assert out2["lead"]["id"] == out1["lead"]["id"] or out2["lead"]["person_id"] == out1["person"]["id"]


def test_a4_unsubscribe_blocks_send():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "m.db"
        store = AccountStore(db)
        store.upsert_account_from_company({"bitrix_id": "8", "title": "X"})
        out = store.resolve_inbound(
            email="stop@x.ru", bitrix_company_id="8", classification="unsubscribe"
        )
        assert out["account"]["lifecycle_status"] == "BLACKLISTED"
        deliver = MagicMock()
        deliver.is_suppressed.return_value = None
        with patch("modules.consent.ConsentLedgerStore") as C, patch(
            "modules.accounts.AccountStore", return_value=store
        ):
            C.return_value.latest_for_email.return_value = {
                "status": "unsubscribed"
            }
            ok, reason = check_send_allowed("stop@x.ru", company_id="8", deliverability=deliver)
            assert ok is False
            assert "consent" in reason or "BLACKLISTED" in reason or "suppressed" in reason


def test_b_flow_search_cluster_reject_cost():
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialStore(Path(tmp) / "m.db")
        out = store.run_search(
            company_title="Demo",
            sources=["web_import"],
            imports=[
                {
                    "source": "web_import",
                    "full_name": "Петр Сидоров",
                    "profile_url": "https://example.com/1",
                    "role": "директор",
                },
                {
                    "source": "web_import",
                    "full_name": "Петр  Сидоров",
                    "profile_url": "https://example.com/2",
                    "role": "CEO",
                },
            ],
        )
        assert out["ok"]
        assert out["run"]["cost_estimate"] >= 0
        clustered = [c for c in out["candidates"] if c.get("cluster_id")]
        assert clustered
        cid = out["candidates"][0]["id"]
        store.set_candidate_status(cid, "rejected")
        try:
            store.create_action_task(candidate_id=cid)
            raised = False
        except ValueError:
            raised = True
        assert raised
        assert "missing_roles" in out["coverage"]


def test_video_approval_required_before_private_upload():
    with tempfile.TemporaryDirectory() as tmp:
        store = VideoStudioStore(Path(tmp) / "m.db")
        draft = store.create_draft(title="Пилот 60с", brief="Для ломбардов")
        blocked = store.queue_private_upload(draft["id"])
        assert blocked["ok"] is False
        assert blocked["error"] == "approval_required"
        store.set_status(draft["id"], "approved")
        ok = store.queue_private_upload(draft["id"])
        assert ok["ok"] is True
        assert ok["draft"]["status"] == "uploaded_private"
        assert ok["youtube_upload"] is False


def test_classify_positive_stops_sequence_flag():
    classified = classify_reply(subject="Re: выплаты", body="Интересно, давайте созвонимся")
    assert classified.should_stop_sequence or classified.classification in (
        "positive_interest",
        "human_unclassified",
        "forwarded",
    )
