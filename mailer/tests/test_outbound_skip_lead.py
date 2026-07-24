"""Lead email only for inbound; outbound is skipped (lightweight policy module)."""

from __future__ import annotations

from mailer.post_call_policy import is_outbound_call


def test_is_outbound_helpers():
    assert is_outbound_call({"context_name": "outbound"}) is True
    assert is_outbound_call({"call_direction": "outbound"}) is True
    assert is_outbound_call({"aava_outbound": "1"}) is True
    assert is_outbound_call({"context_name": "default"}) is False
    assert is_outbound_call({}) is False
