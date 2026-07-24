"""Campaign classification + sheet helpers."""

from __future__ import annotations

import classify
import sheets_io


def test_classify_booked():
    conv = [
        {"role": "assistant", "content": "Готово, встреча зафиксирована на завтра 15:00. Приглашение отправлено на вашу почту."},
        {"role": "user", "content": "Отлично, спасибо"},
    ]
    out = classify.classify_rules(conv, duration=90)
    assert out["interest"] == "yes"
    assert "записан на консультацию" in out["note"]


def test_classify_interest():
    conv = [
        {"role": "assistant", "content": "Вам интересны массовые выплаты?"},
        {"role": "user", "content": "Да, интересно, пусть менеджер перезвонит"},
    ]
    out = classify.classify_rules(conv, duration=40)
    assert out["interest"] == "yes"
    assert "ИНТЕРЕСНО" in out["note"]


def test_classify_negative():
    conv = [{"role": "user", "content": "Нет, не интересно, спасибо"}]
    out = classify.classify_rules(conv, duration=25)
    assert out["interest"] == "no"
    assert "НЕ ИНТЕРЕСНО" in out["note"]


def test_classify_ignores_assistant_only_interest_words():
    conv = [
        {
            "role": "assistant",
            "content": "Здравствуйте! Удобно пару минут? Звоню по теме массовых выплат.",
        }
    ]
    out = classify.classify_rules(conv, duration=12)
    assert out["interest"] == "no"
    assert "НЕ ДОЗВОН" in out["note"]


def test_classify_skips_llm_without_user_speech(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("LLM must not run without user speech")

    monkeypatch.setattr(classify, "classify_llm", boom)
    conv = [{"role": "assistant", "content": "Здравствуйте! Удобно пару минут?"}]
    out = classify.classify(conv, duration=11, outcome="completed")
    assert out["method"].startswith("rules_")
    assert out["interest"] == "no"


def test_col_letter():
    assert sheets_io._col_letter(0) == "A"
    assert sheets_io._col_letter(22) == "W"
