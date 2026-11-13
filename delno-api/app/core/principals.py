"""Map DELNO request context → Second Brain principal IDs."""

from __future__ import annotations

# Legacy brain names kept as aliases during migration.
PRINCIPAL_VOICE_PUBLIC = "service:delno-voice-public"
PRINCIPAL_VOICE_OFFICE = "service:delno-voice-office"
PRINCIPAL_WIDGET_GUEST = "service:delno-widget-guest"
PRINCIPAL_TEXT_GUEST = "service:delno-text-guest"
PRINCIPAL_TEXT_OWNER = "service:delno-text-owner"
PRINCIPAL_ADMIN = "service:delno-admin"

LEGACY_ALIASES: dict[str, str] = {
    PRINCIPAL_VOICE_PUBLIC: "service:voice-public",
    PRINCIPAL_VOICE_OFFICE: "service:voice-office",
    PRINCIPAL_WIDGET_GUEST: "service:text-guest",
    PRINCIPAL_TEXT_GUEST: "service:text-guest",
    PRINCIPAL_TEXT_OWNER: "service:text-owner",
}


def principal_for_operator(*, role: str, is_owner_context: bool = True) -> str:
    """Cabinet AI Operator — owner sees full tenant KB."""
    if role in ("platform_admin", "tenant_owner", "tenant_admin"):
        return PRINCIPAL_TEXT_OWNER
    if is_owner_context:
        return PRINCIPAL_TEXT_OWNER
    return PRINCIPAL_TEXT_GUEST


def principal_for_public_channel(channel: str) -> str:
    mapping = {
        "widget": PRINCIPAL_WIDGET_GUEST,
        "voice_inbound": PRINCIPAL_VOICE_PUBLIC,
        "telegram_guest": PRINCIPAL_TEXT_GUEST,
        "max_guest": PRINCIPAL_TEXT_GUEST,
    }
    return mapping.get(channel, PRINCIPAL_WIDGET_GUEST)


def brain_principal_id(delno_principal: str, *, use_legacy: bool = True) -> str:
    """Return principal id accepted by brain_platform on prod (legacy names)."""
    if use_legacy and delno_principal in LEGACY_ALIASES:
        return LEGACY_ALIASES[delno_principal]
    return delno_principal
