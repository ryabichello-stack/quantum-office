"""Pydantic models for Second Brain document / chunk / audit security contracts."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator


class Visibility(str, Enum):
    PUBLIC = "public"
    COMPANY = "company"
    TEAM = "team"  # concrete value is team:<name> in frontmatter string form
    RESTRICTED = "restricted"
    SECRET = "secret"


class PublicationStatus(str, Enum):
    UNPUBLISHED = "unpublished"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REVOKED = "revoked"


class DocumentStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    QUARANTINE = "quarantine"


class ClassificationLevel(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    SECRET = "secret"


class ACL(BaseModel):
    allow_users: list[str] = Field(default_factory=list)
    allow_groups: list[str] = Field(default_factory=list)
    allow_services: list[str] = Field(default_factory=list)
    deny_users: list[str] = Field(default_factory=list)
    deny_groups: list[str] = Field(default_factory=list)

    def has_explicit_allow(self) -> bool:
        return bool(self.allow_users or self.allow_groups or self.allow_services)


class Classification(BaseModel):
    level: ClassificationLevel = ClassificationLevel.INTERNAL
    contains_personal_data: bool = False
    contains_bank_secret: bool = False
    contains_credentials: bool = False


class Publication(BaseModel):
    status: PublicationStatus = PublicationStatus.UNPUBLISHED
    approved_by: str | None = None
    approved_at: datetime | None = None
    public_version: int | None = None

    @model_validator(mode="after")
    def published_requires_approval(self) -> Publication:
        if self.status == PublicationStatus.PUBLISHED:
            if not self.approved_by or self.approved_at is None:
                raise ValueError(
                    "publication.status=published requires approved_by and approved_at"
                )
            if self.public_version is None:
                raise ValueError("publication.status=published requires public_version")
        return self


class AIProcessingPolicy(BaseModel):
    external_llm_allowed: bool = False
    external_embedding_allowed: bool = False
    local_processing_required: bool = True


class DocumentFrontmatter(BaseModel):
    """Canonical document metadata (security-complete)."""

    id: str
    tenant_id: str
    title: str
    type: str
    visibility: str
    acl: ACL = Field(default_factory=ACL)
    classification: Classification = Field(default_factory=Classification)
    publication: Publication = Field(default_factory=Publication)
    channels: list[str] = Field(default_factory=list)
    ai_processing: AIProcessingPolicy = Field(default_factory=AIProcessingPolicy)
    owner: str | None = None
    created: str | None = None
    updated: str | None = None
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.ACTIVE
    version: int = 1
    acl_revision: int = 1
    source: str | None = None

    @field_validator("tenant_id")
    @classmethod
    def tenant_required(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("tenant_id is required")
        return v.strip()

    @field_validator("visibility")
    @classmethod
    def visibility_shape(cls, v: str) -> str:
        allowed_prefix = ("public", "company", "restricted", "secret")
        if v in allowed_prefix:
            return v
        if v.startswith("team:") and len(v) > 5:
            return v
        raise ValueError(
            f"invalid visibility {v!r}; expected public|company|team:<name>|restricted|secret"
        )

    @model_validator(mode="after")
    def enforce_security_invariants(self) -> DocumentFrontmatter:
        if self.visibility == "restricted" and not self.acl.has_explicit_allow():
            raise ValueError(
                "visibility=restricted requires non-empty allow_users|allow_groups|allow_services"
            )

        if self.visibility == "public":
            if self.publication.status != PublicationStatus.PUBLISHED:
                raise ValueError(
                    "visibility=public requires publication.status=published "
                    "(manual approval only)"
                )

        if self.classification.contains_credentials and self.status != DocumentStatus.QUARANTINE:
            # Credentials must not be auto-indexed as active.
            raise ValueError(
                "documents with contains_credentials must have status=quarantine "
                "until manually cleared"
            )

        if self.visibility in ("restricted", "secret"):
            if self.ai_processing.external_embedding_allowed or self.ai_processing.external_llm_allowed:
                raise ValueError(
                    "restricted/secret must not allow external embedding/LLM by default policy"
                )
            if not self.ai_processing.local_processing_required:
                raise ValueError("restricted/secret require local_processing_required=true")

        return self

    def is_publishable_to_public_index(self) -> bool:
        return (
            self.visibility == "public"
            and self.publication.status == PublicationStatus.PUBLISHED
            and self.publication.approved_by is not None
            and self.publication.approved_at is not None
            and self.status == DocumentStatus.ACTIVE
            and not self.classification.contains_credentials
        )


class ChunkIndexRecord(BaseModel):
    """Indexed chunk must inherit document security fields."""

    chunk_id: str
    document_id: str
    tenant_id: str
    visibility: str
    allowed_user_ids: list[str] = Field(default_factory=list)
    allowed_group_ids: list[str] = Field(default_factory=list)
    allowed_service_ids: list[str] = Field(default_factory=list)
    classification: ClassificationLevel
    acl_revision: int
    document_status: DocumentStatus
    document_version: int
    embedding: list[float] = Field(default_factory=list)

    @model_validator(mode="after")
    def required_security_fields(self) -> ChunkIndexRecord:
        missing = []
        for name in ("chunk_id", "document_id", "tenant_id"):
            if not getattr(self, name):
                missing.append(name)
        if self.acl_revision < 1:
            missing.append("acl_revision")
        if self.document_version < 1:
            missing.append("document_version")
        if missing:
            raise ValueError(f"chunk missing required security fields: {missing}")
        return self


class AuditRecord(BaseModel):
    """Audit must not store full sensitive query text by default."""

    principal_id: str
    tenant_id: str
    query_hash: str
    query_preview_redacted: str
    retrieved_doc_ids: list[str] = Field(default_factory=list)
    denied_doc_count: int = 0
    purpose: str
    timestamp: datetime
    request_id: str
    # Full query is intentionally absent from the default audit model.


class CacheKeyParts(BaseModel):
    tenant_id: str
    principal_id: str
    groups: list[str] = Field(default_factory=list)
    permission_revision: int
    query: str
    search_mode: str
    index_revision: int


class ContactRecord(BaseModel):
    """Canonical office contact — email, phone, title, company."""

    id: str
    tenant_id: str
    display_name: str
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    title: str | None = None
    company_name: str | None = None
    company_entity_id: str | None = None
    visibility: str = "company"
    acl: ACL = Field(default_factory=ACL)
    classification: Classification = Field(
        default_factory=lambda: Classification(
            level=ClassificationLevel.CONFIDENTIAL,
            contains_personal_data=True,
        )
    )
    project_ids: list[str] = Field(default_factory=list)
    acl_revision: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE

    @model_validator(mode="after")
    def contact_security(self) -> ContactRecord:
        if not self.tenant_id:
            raise ValueError("tenant_id required")
        if not self.emails and not self.phones:
            raise ValueError("contact requires at least one email or phone")
        if self.visibility == "public":
            raise ValueError("contacts with PII must not be visibility=public")
        if self.visibility == "restricted" and not self.acl.has_explicit_allow():
            raise ValueError("restricted contact requires ACL allow-list")
        if not self.classification.contains_personal_data:
            raise ValueError("contacts must flag contains_personal_data=true")
        return self


class EmailMessageRecord(BaseModel):
    """Single inbound/outbound message feeding the operational corpus."""

    id: str
    tenant_id: str
    message_id: str
    direction: str  # inbound | outbound
    thread_id: str
    subject: str
    from_email: str
    to_emails: list[str] = Field(default_factory=list)
    cc_emails: list[str] = Field(default_factory=list)
    sent_at: datetime | None = None
    project_id: str | None = None
    visibility: str = "restricted"
    acl: ACL = Field(default_factory=ACL)
    classification: Classification = Field(
        default_factory=lambda: Classification(
            level=ClassificationLevel.CONFIDENTIAL,
            contains_personal_data=True,
        )
    )
    body_hash: str
    attachment_file_ids: list[str] = Field(default_factory=list)
    acl_revision: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE

    @field_validator("direction")
    @classmethod
    def direction_ok(cls, v: str) -> str:
        if v not in ("inbound", "outbound"):
            raise ValueError("direction must be inbound|outbound")
        return v

    @model_validator(mode="after")
    def mail_security(self) -> EmailMessageRecord:
        if self.visibility == "public":
            raise ValueError("email must not be auto-public")
        if self.visibility == "restricted" and not self.acl.has_explicit_allow():
            raise ValueError("restricted email requires ACL allow-list")
        return self


class FileAssetRecord(BaseModel):
    """Server file or mail attachment indexed into the knowledge corpus."""

    id: str
    tenant_id: str
    path: str
    filename: str
    content_hash: str
    source: str  # server_root | mail_attachment | vault
    project_id: str | None = None
    visibility: str = "company"
    acl: ACL = Field(default_factory=ACL)
    classification: Classification = Field(default_factory=Classification)
    acl_revision: int = 1
    status: DocumentStatus = DocumentStatus.ACTIVE

    @model_validator(mode="after")
    def file_security(self) -> FileAssetRecord:
        if not self.tenant_id or not self.path or not self.content_hash:
            raise ValueError("tenant_id, path, content_hash required")
        if self.visibility == "restricted" and not self.acl.has_explicit_allow():
            raise ValueError("restricted file requires ACL allow-list")
        if self.visibility == "public":
            raise ValueError("server files are not auto-public; use manual publish flow")
        return self


class ThreadRecord(BaseModel):
    """Correspondence / discussion thread linked to people and projects."""

    id: str
    tenant_id: str
    subject: str
    channel: str  # email | meeting | discussion
    project_id: str | None = None
    participant_contact_ids: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)
    last_message_at: datetime | None = None
    visibility: str = "restricted"
    acl: ACL = Field(default_factory=ACL)
    topics: list[str] = Field(default_factory=list)
    acl_revision: int = 1

    @model_validator(mode="after")
    def thread_security(self) -> ThreadRecord:
        if self.visibility == "restricted" and not self.acl.has_explicit_allow():
            raise ValueError("restricted thread requires ACL allow-list")
        if self.visibility == "public":
            raise ValueError("threads must not be public without manual publish")
        return self


PrincipalId = Annotated[str, Field(pattern=r"^(user|group|service):.+")]
