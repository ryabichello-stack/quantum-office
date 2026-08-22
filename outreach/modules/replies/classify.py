"""Rule-based inbound reply classification (no LLM)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from email.message import Message
from typing import Any


@dataclass
class ReplyClass:
    classification: str
    confidence: float
    should_stop_sequence: bool
    should_notify: bool
    should_create_task: bool
    reason: str = ""
    should_pause_sequence: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "confidence": self.confidence,
            "should_stop_sequence": self.should_stop_sequence,
            "should_pause_sequence": self.should_pause_sequence,
            "should_notify": self.should_notify,
            "should_create_task": self.should_create_task,
            "reason": self.reason,
        }


_UNSUB = re.compile(
    r"\b(отпис|unsubscribe|не\s*пишите|не\s*пишите|удалите|stop\s*mail|"
    r"remove\s*me|не\s*рассыла|больше\s*не\s*пишите)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(неинтерес|не\s*интерес|нет\s*необходим|не\s*актуаль|"
    r"не\s*нужн|отказ|не\s*звоните|не\s*надо|not\s*interested|"
    r"no\s*thank|already\s*have)\b",
    re.I,
)
_OOO = re.compile(
    r"\b(out\s*of\s*office|автоответ|автоматическ|в\s*отпуске|"
    r"буду\s*отсут|отсутствую|на\s*больнич|ooo|vacation|"
    r"away\s*from|вернус[ь]?)\b",
    re.I,
)
_FORWARD = re.compile(
    r"\b(перешлю|перенаправ|обратитесь|коллег|ответственн|"
    r"forward(ed)?|cc['’]?d|направьте)\b",
    re.I,
)
_POSITIVE = re.compile(
    r"\b(интересн|давайте|готов[аы]?|встреча|созвон|предложен|"
    r"тариф|интеграц|демо|КП|коммерческ|когда\s*удобн|"
    r"interested|let['’]?s\s*talk|schedule|meeting)\b",
    re.I,
)


def classify_reply(
    *,
    subject: str = "",
    body: str = "",
    msg: Message | None = None,
) -> ReplyClass:
    """Classify inbound mail. Prefer headers for auto/bounce, then text."""
    subj = subject or ""
    text = f"{subj}\n{body or ''}"

    if msg is not None:
        auto = (msg.get("Auto-Submitted") or "").strip().lower()
        prec = (msg.get("Precedence") or "").strip().lower()
        xauto = (msg.get("X-Autoreply") or msg.get("X-Auto-Response-Suppress") or "").strip()
        if auto and auto not in ("no",):
            return ReplyClass(
                "automatic", 0.95, False, False, False, "Auto-Submitted", should_pause_sequence=True
            )
        if prec in ("bulk", "junk", "list"):
            return ReplyClass(
                "automatic",
                0.85,
                False,
                False,
                False,
                f"Precedence:{prec}",
                should_pause_sequence=True,
            )
        if xauto:
            return ReplyClass(
                "automatic", 0.9, False, False, False, "X-Autoreply", should_pause_sequence=True
            )
        ctype = (msg.get_content_type() or "").lower()
        if "multipart/report" in ctype or "delivery-status" in ctype:
            return ReplyClass("bounce", 0.95, True, False, False, "multipart/report")

    if _UNSUB.search(text):
        return ReplyClass("unsubscribe", 0.92, True, True, False, "unsub_keywords")
    if _OOO.search(text):
        return ReplyClass(
            "out_of_office",
            0.88,
            False,
            False,
            False,
            "ooo_keywords",
            should_pause_sequence=True,
        )
    if _NEGATIVE.search(text):
        return ReplyClass("negative", 0.8, True, True, True, "negative_keywords")
    if _FORWARD.search(text):
        return ReplyClass("forwarded", 0.7, True, True, True, "forward_keywords")
    if _POSITIVE.search(text):
        return ReplyClass("positive_interest", 0.75, True, True, True, "positive_keywords")

    # Short non-empty human-looking reply → unclassified for manager
    body_s = (body or "").strip()
    if len(body_s) >= 8:
        return ReplyClass("human_unclassified", 0.55, True, True, True, "human_fallback")
    if body_s:
        return ReplyClass("human_unclassified", 0.5, True, True, True, "short_human")
    return ReplyClass("unknown", 0.4, False, False, False, "empty")
