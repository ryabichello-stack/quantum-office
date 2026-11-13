"""Physical/logical index-zone guards (B4 lite).

Mail/PII and restricted content must never land in the public zone.
Full physical schema split (brain_public / brain_private) is prepared in
schema_postgres.sql; runtime still uses index_zone column + these guards.
"""

from __future__ import annotations

from typing import Any

PUBLIC_ZONE = "public"
PRIVATE_ZONE = "private"
SECRET_ZONE = "secret"

# Document types that are never public-zone material
NEVER_PUBLIC_TYPES = frozenset(
    {
        "email",
        "mail",
        "thread",
        "contact",
        "contact_note",
        "calendar",
        "crm_note",
    }
)

NEVER_PUBLIC_VISIBILITIES = frozenset({"restricted", "secret", "private"})


def coerce_index_zone(
    *,
    doc_type: str,
    visibility: str,
    index_zone: str | None,
    classification: dict[str, Any] | None = None,
    publication: dict[str, Any] | None = None,
) -> str:
    """Return a safe index_zone for upsert. Never promotes mail/PII to public."""
    zone = (index_zone or PRIVATE_ZONE).strip().lower() or PRIVATE_ZONE
    if zone not in (PUBLIC_ZONE, PRIVATE_ZONE, SECRET_ZONE):
        zone = PRIVATE_ZONE

    dtype = (doc_type or "").strip().lower()
    vis = (visibility or "").strip().lower()
    classification = classification or {}
    publication = publication or {}

    level = str(classification.get("level") or "").lower()
    contains_pii = bool(classification.get("contains_personal_data"))
    approved_public = bool(
        publication.get("manual_approve")
        or publication.get("approved")
        or publication.get("public_approved")
    )

    force_private = (
        dtype in NEVER_PUBLIC_TYPES
        or vis in NEVER_PUBLIC_VISIBILITIES
        or level in ("secret", "restricted", "confidential")
        or contains_pii
    )
    if force_private:
        if zone == PUBLIC_ZONE:
            return PRIVATE_ZONE
        return zone if zone in (PRIVATE_ZONE, SECRET_ZONE) else PRIVATE_ZONE

    # Public zone only with explicit visibility=public + manual publish approval
    if zone == PUBLIC_ZONE:
        if vis == "public" and approved_public:
            return PUBLIC_ZONE
        return PRIVATE_ZONE

    return zone


def assert_not_public_leak(*, doc_type: str, visibility: str, index_zone: str) -> None:
    """Raise ValueError if a write would put sensitive material in public zone."""
    safe = coerce_index_zone(
        doc_type=doc_type, visibility=visibility, index_zone=index_zone
    )
    if index_zone == PUBLIC_ZONE and safe != PUBLIC_ZONE:
        raise ValueError(
            f"zone_guard: refusing public zone for type={doc_type!r} visibility={visibility!r}"
        )
