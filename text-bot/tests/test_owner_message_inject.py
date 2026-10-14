"""Secretary must inject owner_message when the model omits the draft/list."""

from __future__ import annotations

import json

from secretary import Secretary


def test_draft_teaser_replaced_with_owner_message():
    owner = (
        "Черновик звонка:\n\n"
        "Номер: 79311031371\n\n"
        "Задача: пригласи на свидание\n\n"
        "Greeting:\n«Здравствуйте, Света!»\n\n"
        "Script:\n1. Представься\n\n"
        "Если ок — напишите «да, звони»."
    )
    payload = json.dumps(
        {"ok": True, "owner_message": owner},
        ensure_ascii=False,
    )
    teaser = (
        "Черновик звонка готов — вижу сценарий ниже. "
        "Если звоним, напишите «да, звони»."
    )
    out = Secretary._ensure_owner_messages_in_reply(teaser, [payload])
    assert out == owner
    assert "Greeting:" in out
    assert "Script:" in out


def test_draft_kept_when_model_already_pasted():
    owner = "Черновик:\n\nGreeting:\n«Hi»\n\nScript:\nStep 1"
    payload = json.dumps({"ok": True, "owner_message": owner}, ensure_ascii=False)
    reply = "Вот сценарий:\n\nGreeting:\n«Hi»\n\nScript:\nStep 1\n\nЖду «да, звони»."
    out = Secretary._ensure_owner_messages_in_reply(reply, [payload])
    assert out == reply


def test_files_list_injected_when_missing():
    owner = "Mail.ru Облако\nПуть: /\n\nПапки:\n• 📁 !Банк  →  /!Банк"
    payload = json.dumps({"ok": True, "owner_message": owner}, ensure_ascii=False)
    out = Secretary._ensure_owner_messages_in_reply(
        "Список папок готов, смотрите ниже.", [payload]
    )
    assert out == owner
