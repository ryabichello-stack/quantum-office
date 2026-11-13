import pytest

from app.core.principals import (
    PRINCIPAL_TEXT_GUEST,
    PRINCIPAL_TEXT_OWNER,
    PRINCIPAL_VOICE_PUBLIC,
    brain_principal_id,
    principal_for_operator,
    principal_for_public_channel,
)


def test_principal_for_operator_owner_roles():
    assert principal_for_operator(role="tenant_owner") == PRINCIPAL_TEXT_OWNER
    assert principal_for_operator(role="platform_admin") == PRINCIPAL_TEXT_OWNER
    assert principal_for_operator(role="manager", is_owner_context=False) == PRINCIPAL_TEXT_GUEST


def test_principal_for_public_channel():
    assert principal_for_public_channel("widget").endswith("widget-guest")
    assert principal_for_public_channel("voice_inbound").endswith("voice-public")


def test_brain_legacy_alias():
    assert brain_principal_id(PRINCIPAL_VOICE_PUBLIC, use_legacy=True) == "service:voice-public"
    assert brain_principal_id(PRINCIPAL_TEXT_OWNER, use_legacy=True) == "service:text-owner"
    from app.core.principals import PRINCIPAL_WIDGET_GUEST

    assert brain_principal_id(PRINCIPAL_WIDGET_GUEST, use_legacy=True) == "service:text-guest"
    assert brain_principal_id("service:custom", use_legacy=True) == "service:custom"
