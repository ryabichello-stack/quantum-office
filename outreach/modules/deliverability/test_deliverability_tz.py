"""TZ acceptance tests for deliverability / reputation protection."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.deliverability.bounce import classify_bounce
from modules.delivery_errors import DeliveryErrorStore
from modules.policy import ContactPolicyStore
from modules.reputation_guard import ReputationGuardStore
from modules.sending_accounts import SendingAccountsStore


YANDEX_554 = (
    "SMTP error from remote mail server after end of data:\n"
    "554 5.7.1 Message rejected under suspicion of SPAM; https://ya.cc/1IrBc"
)


class TzDeliverabilityTests(unittest.TestCase):
    def test_554_is_policy_not_hard(self) -> None:
        c = classify_bounce(YANDEX_554)
        self.assertEqual(c.category, "policy")
        self.assertNotEqual(c.category, "hard")
        self.assertFalse(c.retry)
        self.assertFalse(c.pause_mailbox)

    def test_hard_550_user_unknown(self) -> None:
        c = classify_bounce("550 5.1.1 The email account that you tried to reach does not exist")
        self.assertEqual(c.category, "hard")
        self.assertTrue(c.suppress)
        self.assertFalse(c.retry)

    def test_protected_domain_blocks_marketing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "m.db"
            with mock.patch.dict(os.environ, {"MAIL_USERNAME": "office@quantumlabs.ru"}):
                store = SendingAccountsStore(db)
            self.assertIn("quantumlabs.ru", store.list_protected_domains())
            ok, why, _ = store.marketing_send_gate(from_email="office@quantumlabs.ru")
            self.assertFalse(ok)
            self.assertIn("protected_domain", why)

    def test_override_allows_protected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = SendingAccountsStore(Path(tmp) / "m.db")
            ok, why, _ = store.marketing_send_gate(
                from_email="office@quantumlabs.ru",
                allow_protected_override=True,
            )
            self.assertTrue(ok)
            self.assertEqual(why, "override_protected")

    def test_delivery_error_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DeliveryErrorStore(Path(tmp) / "m.db")
            a = store.record(
                email="a@yandex.ru",
                raw=YANDEX_554,
                message_id="mid-1",
                outreach_id="oneshot-1",
            )
            b = store.record(
                email="a@yandex.ru",
                raw=YANDEX_554,
                message_id="mid-1",
                outreach_id="oneshot-1",
            )
            self.assertFalse(a["duplicate"])
            self.assertTrue(b["duplicate"])
            self.assertEqual(a["id"], b["id"])
            self.assertEqual(a["category"], "policy")

    def test_consent_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pol = ContactPolicyStore(Path(tmp) / "m.db")
            pol.upsert("c1", primary_email="x@example.com")
            ok, why = pol.allow_marketing_consent("c1", require_consent=True)
            self.assertFalse(ok)
            self.assertIn("consent", why)
            pol.set_consent("c1", status="granted", source="test", evidence="unit")
            ok2, why2 = pol.allow_marketing_consent("c1", require_consent=True)
            self.assertTrue(ok2)
            self.assertEqual(why2, "consent:granted")

    def test_unsubscribe_denies_marketing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pol = ContactPolicyStore(Path(tmp) / "m.db")
            pol.set_consent("c2", status="granted", source="test")
            pol.note_unsubscribe("c2")
            ok, why = pol.allow_marketing_consent("c2", require_consent=True)
            self.assertFalse(ok)

    def test_campaign_pause_on_policy_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "m.db"
            errors = DeliveryErrorStore(db)
            guard = ReputationGuardStore(db)
            for i in range(2):
                errors.record(
                    email=f"u{i}@yandex.ru",
                    raw=YANDEX_554,
                    message_id=f"m-{i}",
                    campaign="lombards",
                )
            out = guard.evaluate_after_policy(campaign="lombards")
            self.assertTrue(out["paused"])
            paused, reason = guard.is_campaign_paused("lombards")
            self.assertTrue(paused)
            self.assertIn("policy_events_today", reason)


if __name__ == "__main__":
    unittest.main()
