"""Send guards + orchestrator journey stop."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from modules.accounts import AccountStore
from modules.consent import ConsentLedgerStore
from modules.orchestrator import OrchestratorStore
from send_guards import check_send_allowed


def test_check_send_allowed_consent_and_blacklist():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "m.db"
        consent = ConsentLedgerStore(db)
        consent.record(email="x@y.ru", status="unsubscribed", reason="test")

        deliver = MagicMock()
        deliver.is_suppressed.return_value = None

        with patch("modules.consent.ConsentLedgerStore", return_value=consent), patch(
            "modules.accounts.AccountStore"
        ) as Acc:
            Acc.return_value.get_account_by_bitrix.return_value = None
            Acc.return_value.find_person_by_email.return_value = None
            ok, reason = check_send_allowed("x@y.ru", deliverability=deliver)
            assert ok is False
            assert reason.startswith("consent:")

        deliver.is_suppressed.return_value = "manual"
        ok2, reason2 = check_send_allowed("a@b.ru", deliverability=deliver)
        assert ok2 is False
        assert "suppressed" in reason2

        acc = AccountStore(db)
        acc.upsert_account_from_company({"bitrix_id": "9", "title": "Z"})
        acc.set_lifecycle(acc.get_account_by_bitrix("9")["id"], "BLACKLISTED")
        deliver.is_suppressed.return_value = None
        with patch("modules.consent.ConsentLedgerStore") as C, patch(
            "modules.accounts.AccountStore", return_value=acc
        ):
            C.return_value.latest_for_email.return_value = None
            ok3, reason3 = check_send_allowed(
                "z@z.ru", company_id="9", deliverability=deliver
            )
            assert ok3 is False
            assert reason3 == "account:BLACKLISTED"


def test_orchestrator_enroll_and_stop_on_reply():
    with tempfile.TemporaryDirectory() as tmp:
        store = OrchestratorStore(Path(tmp) / "m.db")
        enr = store.enroll(email="lead@co.ru", company_id="42")
        assert enr["status"] == "active"
        preview = store.dry_run_preview(email="lead@co.ru", company_id="42")
        assert preview["dry_run"] is True
        assert "journey" in preview

        with patch("modules.sequences.SequenceStore") as Seq:
            Seq.return_value.stop.return_value = 1
            out = store.on_inbound_reply(
                email="lead@co.ru",
                company_id="42",
                classification="positive_interest",
                stop_sequences=True,
            )
            assert out["stopped_enrollments"] >= 1
            assert out["stopped_sequences"] == 1
            Seq.return_value.stop.assert_called()

        active = [e for e in store.list_enrollments() if e["status"] == "active"]
        assert not any(e["email"] == "lead@co.ru" for e in active)
