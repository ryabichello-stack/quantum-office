"""Permission principals, ACL filter building, cache keys, audit helpers."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from brain_platform.schemas.models import (
    ACL,
    AuditRecord,
    CacheKeyParts,
    ChunkIndexRecord,
    DocumentFrontmatter,
)


SearchBackend = Literal["keyword", "vector", "graph"]


SERVICE_PRINCIPALS = (
    "service:voice-public",
    "service:voice-office",
    "service:text-secretary",
    "service:text-guest",
    "service:outreach",
    "service:cursor-admin",
)


@dataclass(frozen=True)
class Principal:
    """Authenticated identity; tenant always from token, never from request body."""

    principal_id: str
    tenant_id: str
    groups: tuple[str, ...] = ()
    user_id: str | None = None
    is_admin: bool = False
    permission_revision: int = 1

    def __post_init__(self) -> None:
        if not self.tenant_id:
            raise ValueError("tenant_id must come from auth token")
        if not self.principal_id:
            raise ValueError("principal_id required")


@dataclass
class ACLFilter:
    """Mandatory filter pushed into each search backend query."""

    tenant_id: str
    principal_id: str
    allowed_visibilities: set[str] = field(default_factory=set)
    allowed_channels: set[str] = field(default_factory=set)
    require_assistant_safe: bool = False
    allow_all_in_tenant: bool = False  # only cursor-admin with personal admin auth
    deny_all: bool = False

    def to_sql_predicate(self) -> str:
        """Illustrative SQL fragment — backends must embed equivalent constraints."""
        if self.deny_all:
            return "FALSE /* deny all */"
        parts = [f"tenant_id = '{self._esc(self.tenant_id)}'"]
        if self.allow_all_in_tenant:
            return " AND ".join(parts)
        vis = ", ".join(f"'{self._esc(v)}'" for v in sorted(self.allowed_visibilities)) or "NULL"
        parts.append(f"(visibility IN ({vis}) OR _acl_principal_allowed('{self._esc(self.principal_id)}'))")
        if self.require_assistant_safe:
            parts.append("'office-assistant' = ANY(channels)")
        return " AND ".join(parts)

    @staticmethod
    def _esc(value: str) -> str:
        return value.replace("'", "''")


def resolve_principal_policy(principal: Principal) -> ACLFilter:
    """Default deny. Explicit allow lists per service principal (ADR §4.12)."""
    pid = principal.principal_id

    if pid not in SERVICE_PRINCIPALS and not pid.startswith("user:"):
        return ACLFilter(
            tenant_id=principal.tenant_id,
            principal_id=pid,
            deny_all=True,
        )

    if pid == "service:voice-public":
        return ACLFilter(
            tenant_id=principal.tenant_id,
            principal_id=pid,
            allowed_visibilities={"public"},
            allowed_channels=set(),
        )

    if pid in ("service:voice-office", "service:text-secretary", "service:text-guest"):
        return ACLFilter(
            tenant_id=principal.tenant_id,
            principal_id=pid,
            allowed_visibilities={"public"},
            allowed_channels={"office-assistant"},
            require_assistant_safe=True,
        )

    if pid == "service:outreach":
        return ACLFilter(
            tenant_id=principal.tenant_id,
            principal_id=pid,
            allowed_visibilities={"public", "team:sales"},
            allowed_channels={"outreach"},
        )

    if pid == "service:cursor-admin":
        if principal.is_admin and principal.user_id:
            return ACLFilter(
                tenant_id=principal.tenant_id,
                principal_id=pid,
                allow_all_in_tenant=True,
            )
        return ACLFilter(
            tenant_id=principal.tenant_id,
            principal_id=pid,
            deny_all=True,
        )

    # Authenticated human user — still not blanket company; groups must match ACL.
    return ACLFilter(
        tenant_id=principal.tenant_id,
        principal_id=pid,
        allowed_visibilities={"public", "company"},
        allowed_channels=set(principal.groups),
    )


def tenant_from_token_claims(claims: dict[str, Any]) -> str:
    """API must take tenant from auth claims, never from untrusted request body."""
    tenant = claims.get("tenant_id")
    if not tenant or not isinstance(tenant, str):
        raise PermissionError("tenant_id missing from principal token")
    return tenant


def reject_client_supplied_tenant(body: dict[str, Any], claims: dict[str, Any]) -> str:
    body_tenant = body.get("tenant_id")
    token_tenant = tenant_from_token_claims(claims)
    if body_tenant is not None and body_tenant != token_tenant:
        raise PermissionError("client-supplied tenant_id does not match token")
    return token_tenant


def document_readable(doc: DocumentFrontmatter, principal: Principal) -> bool:
    """Defense-in-depth check after in-query filtering."""
    filt = resolve_principal_policy(principal)
    if filt.deny_all:
        return False
    if doc.tenant_id != principal.tenant_id:
        return False
    if filt.allow_all_in_tenant:
        return True

    if _denied_by_acl(doc.acl, principal):
        return False

    # Office bots: published public + curated assistant-safe channel (not blanket company).
    if filt.require_assistant_safe:
        if doc.visibility == "public" and doc.is_publishable_to_public_index():
            return True
        if "office-assistant" in doc.channels:
            if doc.visibility == "restricted":
                return _allowed_by_acl(doc.acl, principal)
            if doc.visibility in ("company", "public") or doc.visibility.startswith("team:"):
                return True
        return False

    if doc.visibility == "public":
        return doc.is_publishable_to_public_index()

    if doc.visibility in filt.allowed_visibilities:
        if doc.visibility.startswith("team:"):
            return True
        if doc.visibility == "company":
            # Blanket company is NOT granted to voice/text services.
            return principal.principal_id.startswith("user:")
        return True

    if doc.visibility == "restricted":
        return _allowed_by_acl(doc.acl, principal)

    if doc.visibility == "secret":
        return principal.is_admin and _allowed_by_acl(doc.acl, principal)

    if doc.visibility.startswith("team:"):
        team = doc.visibility.split(":", 1)[1]
        return f"group:{team}" in principal.groups or team in {
            g.removeprefix("group:") for g in principal.groups
        }

    return False


def _allowed_by_acl(acl: ACL, principal: Principal) -> bool:
    if principal.principal_id in acl.allow_users:
        return True
    if principal.principal_id in acl.allow_services:
        return True
    if principal.user_id and f"user:{principal.user_id}" in acl.allow_users:
        return True
    for g in principal.groups:
        gnorm = g if g.startswith("group:") else f"group:{g}"
        if gnorm in acl.allow_groups:
            return True
    return False


def _denied_by_acl(acl: ACL, principal: Principal) -> bool:
    if principal.principal_id in acl.deny_users:
        return True
    if principal.user_id and f"user:{principal.user_id}" in acl.deny_users:
        return True
    for g in principal.groups:
        gnorm = g if g.startswith("group:") else f"group:{g}"
        if gnorm in acl.deny_groups:
            return True
    return False


def build_backend_query(
    backend: SearchBackend,
    principal: Principal,
    query: str,
    *,
    post_filter_only: bool = False,
) -> dict[str, Any]:
    """
    Construct a search plan. post_filter_only=True is REJECTED — ACL must be in-query.
    """
    if post_filter_only:
        raise PermissionError(
            "post-filtering as primary access control is forbidden; "
            "each backend must apply ACL inside the query"
        )
    filt = resolve_principal_policy(principal)
    return {
        "backend": backend,
        "query": query,
        "acl_filter": filt.to_sql_predicate(),
        "tenant_id": principal.tenant_id,
        "post_filter_defense_in_depth": True,
    }


def build_cache_key(parts: CacheKeyParts) -> str:
    payload = {
        "tenant_id": parts.tenant_id,
        "principal_id": parts.principal_id,
        "groups": sorted(parts.groups),
        "permission_revision": parts.permission_revision,
        "query": parts.query,
        "search_mode": parts.search_mode,
        "index_revision": parts.index_revision,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def forbid_query_only_cache_key(query: str) -> None:
    """Guard used in tests/reviews: hash(query) alone is forbidden."""
    raise PermissionError(
        f"cache_key=hash(query) is forbidden; query={query!r} must be scoped by security context"
    )


_REDACT_PATTERNS = [
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"\b\d{10,20}\b"),
    re.compile(r"(?i)(password|token|secret|api[_-]?key)\s*[:=]\s*\S+"),
]


def redact_query_preview(query: str, max_len: int = 80) -> str:
    text = query
    for pat in _REDACT_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    text = text.strip()
    if len(text) > max_len:
        text = text[: max_len - 1] + "…"
    return text


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def make_audit_record(
    *,
    principal: Principal,
    query: str,
    retrieved_doc_ids: list[str],
    denied_doc_count: int,
    purpose: str,
    request_id: str,
    timestamp,
) -> AuditRecord:
    return AuditRecord(
        principal_id=principal.principal_id,
        tenant_id=principal.tenant_id,
        query_hash=query_hash(query),
        query_preview_redacted=redact_query_preview(query),
        retrieved_doc_ids=retrieved_doc_ids,
        denied_doc_count=denied_doc_count,
        purpose=purpose,
        timestamp=timestamp,
        request_id=request_id,
    )


def chunk_inherits_document(
    doc: DocumentFrontmatter,
    chunk_id: str,
    *,
    embedding: list[float] | None = None,
) -> ChunkIndexRecord:
    from brain_platform.schemas.models import ClassificationLevel

    return ChunkIndexRecord(
        chunk_id=chunk_id,
        document_id=doc.id,
        tenant_id=doc.tenant_id,
        visibility=doc.visibility,
        allowed_user_ids=list(doc.acl.allow_users),
        allowed_group_ids=[g.removeprefix("group:") for g in doc.acl.allow_groups],
        allowed_service_ids=list(doc.acl.allow_services),
        classification=doc.classification.level
        if isinstance(doc.classification.level, ClassificationLevel)
        else ClassificationLevel(doc.classification.level),
        acl_revision=doc.acl_revision,
        document_status=doc.status,
        document_version=doc.version,
        embedding=embedding or [],
    )
