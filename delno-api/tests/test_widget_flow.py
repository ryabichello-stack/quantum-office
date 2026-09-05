"""Widget flow helpers."""

from __future__ import annotations

from app.services.widget_flow import normalize_phone, widget_next_step


def test_normalize_phone_russian_formats():
    assert normalize_phone("8 (999) 123-45-67") == "+79991234567"
    assert normalize_phone("9991234567") == "+79991234567"
    assert normalize_phone("abc") is None


def test_widget_next_step_flow():
    assert widget_next_step({}) == "ask_name"
    assert widget_next_step({"visitor_name": "Иван"}) == "ask_phone"
    assert widget_next_step({"visitor_name": "Иван", "lead_id": "x"}) is None
