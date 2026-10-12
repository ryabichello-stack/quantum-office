"""Policy/spam bounce must not pause the whole mailbox on a single event."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.deliverability import DeliverabilityStore, domain_family
from modules.deliverability.bounce import classify_bounce


YANDEX_SPAM = (
    "SMTP error from remote mail server after end of data:\n"
    "554 5.7.1 Message rejected under suspicion of SPAM; https://ya.cc/1IrBc"
)


class PolicyBounceTests(unittest.TestCase):
    def test_classify_policy_does_not_request_mailbox_pause(self) -> None:
        c = classify_bounce(YANDEX_SPAM)
        self.assertEqual(c.category, "policy")
        self.assertEqual(c.reason, "policy_or_spam_block")
        self.assertFalse(c.pause_mailbox)

    def test_yandex_family(self) -> None:
        self.assertEqual(domain_family("yandex.ru"), "yandex")
        self.assertEqual(domain_family("ya.ru"), "yandex")
        self.assertEqual(domain_family("mail.ru"), "mailru")

    def test_single_policy_cools_domain_keeps_mailbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DeliverabilityStore(Path(tmp) / "m.db")
            classified = store.handle_bounce(
                email="lombard.1may@yandex.ru",
                raw_reason=YANDEX_SPAM,
            )
            self.assertEqual(classified.category, "policy")
            paused, reason = store.is_paused()
            self.assertFalse(paused, reason)
            cooled = store.domain_cooldown_reason("other@ya.ru")
            self.assertIsNotNone(cooled)
            # other ISPs still allowed
            self.assertIsNone(store.domain_cooldown_reason("boss@mail.ru"))
            decision = store.decide(
                email="next@yandex.ru",
                settings=None,
                sent_today=0,
                configured_daily_limit=15,
            )
            self.assertFalse(decision.allow)
            self.assertIn("domain_cooldown", decision.reason)
            ok = store.decide(
                email="ok@mail.ru",
                settings=None,
                sent_today=0,
                configured_daily_limit=15,
            )
            self.assertTrue(ok.allow)

    def test_three_isps_trigger_global_pause(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = DeliverabilityStore(Path(tmp) / "m.db")
            for em in ("a@yandex.ru", "b@mail.ru", "c@gmail.com"):
                store.handle_bounce(email=em, raw_reason=YANDEX_SPAM)
            paused, reason = store.is_paused()
            self.assertTrue(paused)
            self.assertIn("policy_isps_today", reason)


if __name__ == "__main__":
    unittest.main()
