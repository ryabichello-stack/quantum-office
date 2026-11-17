"""Files selected by a company for outgoing messages."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.onboarding_upload import OnboardingUpload
from app.models.tenant_folder import TenantFolder
from app.services.tenant_files import resolve_tenant_path, tenant_prefix

MAX_ATTACHMENT_BYTES = 10_000_000
BLOCKED_SUFFIXES = frozenset({".exe", ".bat", ".cmd", ".sh", ".js", ".php", ".dll", ".msi", ".apk"})


def _safe_name(name: str) -> str:
    clean = Path((name or "").replace("\\", "/")).name.strip()
    if not clean or clean in {".", ".."} or Path(clean).suffix.lower() in BLOCKED_SUFFIXES:
        raise ValueError("unsupported_file")
    return clean[:255]


def _folder(db: Session, ctx: TenantContext, folder_id: str | None) -> TenantFolder | None:
    if not folder_id:
        return None
    try:
        parsed = uuid.UUID(folder_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("folder_not_found") from exc
    row = db.query(TenantFolder).filter(TenantFolder.id == parsed, TenantFolder.tenant_id == ctx.tenant_id).one_or_none()
    if row is None:
        raise ValueError("folder_not_found")
    return row


def list_folders(db: Session, ctx: TenantContext) -> list[dict[str, str | None]]:
    rows = db.query(TenantFolder).filter(TenantFolder.tenant_id == ctx.tenant_id).order_by(TenantFolder.name).all()
    return [{"id": str(row.id), "parent_id": str(row.parent_id) if row.parent_id else None, "name": row.name} for row in rows]


def create_folder(db: Session, ctx: TenantContext, name: str, parent_id: str | None = None) -> dict[str, str | None]:
    clean = (name or "").strip()
    if not clean or len(clean) > 120 or clean in {".", ".."} or "/" in clean or "\\" in clean:
        raise ValueError("invalid_folder_name")
    parent = _folder(db, ctx, parent_id)
    siblings = db.query(TenantFolder).filter(TenantFolder.tenant_id == ctx.tenant_id, TenantFolder.parent_id == (parent.id if parent else None)).all()
    if any(row.name.casefold() == clean.casefold() for row in siblings):
        raise ValueError("folder_exists")
    row = TenantFolder(tenant_id=ctx.tenant_id, parent_id=parent.id if parent else None, name=clean)
    db.add(row)
    db.commit()
    return {"id": str(row.id), "parent_id": str(row.parent_id) if row.parent_id else None, "name": row.name}


def delete_folder(db: Session, ctx: TenantContext, folder_id: str) -> None:
    row = _folder(db, ctx, folder_id)
    assert row is not None
    if db.query(TenantFolder).filter(TenantFolder.tenant_id == ctx.tenant_id, TenantFolder.parent_id == row.id).first():
        raise ValueError("folder_not_empty")
    if any((item.meta or {}).get("folder_id") == folder_id for item in _stored_rows(db, ctx)):
        raise ValueError("folder_not_empty")
    db.delete(row)
    db.commit()


def _stored_rows(db: Session, ctx: TenantContext) -> list[OnboardingUpload]:
    return db.query(OnboardingUpload).filter(OnboardingUpload.tenant_id == ctx.tenant_id, OnboardingUpload.parse_status == "stored").all()


async def save_file(db: Session, ctx: TenantContext, upload: UploadFile, folder_id: str | None = None) -> dict[str, Any]:
    name = _safe_name(upload.filename or "")
    folder = _folder(db, ctx, folder_id)
    data = await upload.read(MAX_ATTACHMENT_BYTES + 1)
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("file_empty_or_too_large")
    file_id = uuid.uuid4()
    relative = f"{file_id.hex}{Path(name).suffix.lower()}"
    target = resolve_tenant_path(ctx.tenant_id, zone="uploads", relative=relative, create_parents=True)
    target.write_bytes(data)
    row = OnboardingUpload(
        id=file_id, tenant_id=ctx.tenant_id, file_name=name,
        content_type=upload.content_type, storage_path=str(target),
        size_bytes=len(data), parse_status="stored", meta={"purpose": "outbound", "folder_id": str(folder.id) if folder else None},
    )
    db.add(row)
    db.commit()
    return {"id": str(file_id), "name": name, "bytes": len(data), "folder_id": str(folder.id) if folder else None}


def list_files(db: Session, ctx: TenantContext, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
    rows = (
        db.query(OnboardingUpload)
        .filter(OnboardingUpload.tenant_id == ctx.tenant_id, OnboardingUpload.parse_status == "stored")
        .order_by(OnboardingUpload.created_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
    return [{"id": str(row.id), "name": row.file_name, "bytes": row.size_bytes, "folder_id": (row.meta or {}).get("folder_id")} for row in rows]


def _file_row(db: Session, ctx: TenantContext, file_id: str) -> OnboardingUpload:
    try:
        parsed = uuid.UUID(file_id)
    except (ValueError, TypeError) as exc:
        raise ValueError("file_not_found") from exc
    row = db.query(OnboardingUpload).filter(OnboardingUpload.id == parsed, OnboardingUpload.tenant_id == ctx.tenant_id, OnboardingUpload.parse_status == "stored").one_or_none()
    if row is None:
        raise ValueError("file_not_found")
    path = Path(row.storage_path).resolve()
    try:
        path.relative_to(resolve_tenant_path(ctx.tenant_id, zone="uploads").resolve())
    except ValueError as exc:
        raise ValueError("file_not_found") from exc
    return row


def move_file(db: Session, ctx: TenantContext, file_id: str, folder_id: str | None) -> dict[str, Any]:
    row = _file_row(db, ctx, file_id)
    folder = _folder(db, ctx, folder_id)
    row.meta = {**(row.meta or {}), "folder_id": str(folder.id) if folder else None}
    db.commit()
    return {"id": str(row.id), "name": row.file_name, "bytes": row.size_bytes, "folder_id": row.meta["folder_id"]}


def delete_file(db: Session, ctx: TenantContext, file_id: str) -> None:
    row = _file_row(db, ctx, file_id)
    Path(row.storage_path).unlink(missing_ok=True)
    db.delete(row)
    db.commit()


def download_file(db: Session, ctx: TenantContext, file_id: str) -> tuple[str, bytes, str]:
    row = _file_row(db, ctx, file_id)
    path = Path(row.storage_path)
    if not path.is_file() or path.stat().st_size > MAX_ATTACHMENT_BYTES:
        raise ValueError("file_unavailable")
    return _safe_name(row.file_name), path.read_bytes(), row.content_type or "application/octet-stream"


def create_text_file(db: Session, ctx: TenantContext, name: str, content: str, folder_id: str | None = None) -> dict[str, Any]:
    clean = _safe_name(name)
    if Path(clean).suffix.lower() not in {".txt", ".md", ".csv", ".html"}:
        raise ValueError("unsupported_generated_format")
    data = content.encode("utf-8")
    if not data or len(data) > MAX_ATTACHMENT_BYTES:
        raise ValueError("file_empty_or_too_large")
    folder = _folder(db, ctx, folder_id)
    file_id = uuid.uuid4()
    target = resolve_tenant_path(ctx.tenant_id, zone="uploads", relative=f"{file_id.hex}{Path(clean).suffix.lower()}", create_parents=True)
    target.write_bytes(data)
    row = OnboardingUpload(id=file_id, tenant_id=ctx.tenant_id, file_name=clean, content_type="text/plain; charset=utf-8", storage_path=str(target), size_bytes=len(data), parse_status="stored", meta={"purpose": "generated", "folder_id": str(folder.id) if folder else None})
    db.add(row)
    db.commit()
    return {"id": str(file_id), "name": clean, "bytes": len(data), "folder_id": str(folder.id) if folder else None}


def read_text_file(db: Session, ctx: TenantContext, file_id: str) -> dict[str, str]:
    name, data, _ = download_file(db, ctx, file_id)
    if Path(name).suffix.lower() not in {".txt", ".md", ".csv", ".html", ".json"}:
        raise ValueError("file_requires_parser")
    if len(data) > 100_000:
        raise ValueError("file_too_large_to_read")
    return {"name": name, "content": data.decode("utf-8-sig")}


def attachment_for(db: Session, ctx: TenantContext, file_id: str) -> dict[str, str]:
    row = _file_row(db, ctx, file_id)
    path = Path(row.storage_path).resolve()
    try:
        path.relative_to(tenant_prefix(ctx.tenant_id).resolve())
    except ValueError as exc:
        raise ValueError("file_not_found") from exc
    if not path.is_file() or path.stat().st_size > MAX_ATTACHMENT_BYTES:
        raise ValueError("file_unavailable")
    return {"name": _safe_name(row.file_name), "content_base64": base64.b64encode(path.read_bytes()).decode("ascii")}
