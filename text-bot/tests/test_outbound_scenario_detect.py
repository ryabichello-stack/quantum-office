"""Outbound scenario routing must win over secretary/memory meta."""

from __future__ import annotations

import scenarios as sc


def test_looks_like_outbound_with_phone():
    text = (
        "Позвони на номер +7 (931) 103-13-71 зовут Света "
        "пригласи на свидание от имени Дениса"
    )
    assert sc.looks_like_outbound_request(text) is True


def test_detect_outbound_for_call_request(monkeypatch):
    sc.load_scenarios()
    text = (
        "Позвони на номер +7 (931) 103-13-71 зовут Света "
        "пригласи на свидание от имени Дениса и потом расскажи что тебе ответила"
    )
    active = sc.detect_scenario(text, "owner")
    assert active.id == "outbound"


def test_not_outbound_for_memory_question():
    assert sc.looks_like_outbound_request("Найди в почте договор с Альфой") is False
