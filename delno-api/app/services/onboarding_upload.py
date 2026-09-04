"""O3 — tenant-scoped onboarding file upload + brain extract + draft KB."""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from typing import Any

import httpx
from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.principals import PRINCIPAL_ADMIN
from app.core.tenant import TenantContext
from app.models.conversation import Message
from app.models.onboarding_upload import OnboardingUpload
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import upsert_draft_knowledge
from app.services.onboarding_flow import _merge_tenant_settings, get_onboarding_state

ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".docx",
        ".xlsx",
        ".csv",
        ".txt",
        ".md",
        ".html",
        ".htm",
    }
)

BLOCKED_EXTENSIONS = frozenset(
    {
        ".exe",
        ".bat",
        ".cmd",
        ".sh",
        ".php",
        ".js",
        ".zip",
        ".rar",
        ".7z",
        ".dll",
        ".msi",
        ".apk",
    }
)


def _safe_filename(name: str) -> str:
    base = os.path.basename(name or "upload.bin")
    cleaned = re.sub(r"[^\w.\- ()]", "_", base).strip("._") or "upload.bin"
    return cleaned[:200]


def _extension(name: str) -> str:
    return Path(name.lower()).suffix


def validate_upload_file(filename: str, size_bytes: int) -> str | None:
    settings = get_settings()
    if size_bytes <= 0:
        return "empty_file"
    if size_bytes > settings.onboarding_upload_max_bytes:
        return "file_too_large"
    ext = _extension(filename)
    if ext in BLOCKED_EXTENSIONS:
        return "blocked_type"
    if ext not in ALLOWED_EXTENSIONS:
        return "unsupported_type"
    return None


def _storage_dir(tenant_id: uuid.UUID) -> Path:
    settings = get_settings()
    root = Path(settings.onboarding_upload_dir)
    path = root / str(tenant_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _extract_via_brain(
    data: bytes,
    *,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    settings = get_settings()
    base = (settings.knowledge_base_url or "").strip()
    if not base:
        return {"ok": False, "error": "knowledge_disabled", "text": "", "method": "skipped"}

    url = f"{base.rstrip('/')}/api/brain/ingest/extract"
    headers = {
        "X-Tenant-Id": "delno-api",
        "X-Principal-Id": PRINCIPAL_ADMIN,
    }
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                url,
                files={"file": (filename, data, content_type or "application/octet-stream")},
                headers=headers,
            )
            if response.status_code != 200:
                return {
                    "ok": False,
                    "error": f"extract_http_{response.status_code}",
                    "text": "",
                    "method": "error",
                }
            payload = response.json()
            return {"ok": True, **payload}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)[:200], "text": "", "method": "error"}


def _count_table_rows(text: str) -> int:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return len(lines)


def _build_feedback(filename: str, text: str, *, method: str, error: str) -> str:
    low_name = filename.lower()
    if error == "password_protected" or "encrypted" in method:
        return (
            f"Файл «{filename}» защищён паролем — я не смог его прочитать. "
            "Можете загрузить открытую версию или рассказать содержание здесь."
        )
    if not text or len(text.strip()) < 20:
        return (
            f"Я получил «{filename}», но не нашёл в нём достаточно текста. "
            "Попробуйте другой формат или опишите содержание своими словами."
        )

    rows = _count_table_rows(text)
    if method == "xlsx" or "csv" in method or "прайс" in low_name or "price" in low_name:
        return (
            f"Я изучил «{filename}». "
            f"Нашёл таблицу с ~{rows} строками — данные добавил в черновик знаний."
        )
    if method == "pdf":
        return (
            f"Я изучил PDF «{filename}». "
            f"Извлёк текст (~{len(text.split())} слов) и добавил в черновик."
        )
    return (
        f"Я изучил «{filename}». "
        f"Извлёк текст (~{len(text.split())} слов) и добавил в черновик знаний."
    )


def _append_source_to_draft(tenant: Tenant, source: dict[str, Any]) -> None:
    state = get_onboarding_state(tenant)
    draft = dict(state.get("draft") or {})
    sources = list(draft.get("sources") or [])
    sources.append(source)
    draft["sources"] = sources[-50:]
    _merge_tenant_settings(tenant, {"onboarding_draft": draft})


async def ingest_onboarding_upload(
    db: Session,
    ctx: TenantContext,
    *,
    upload_file: UploadFile,
    conversation_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    filename = _safe_filename(upload_file.filename or "upload.bin")
    data = await upload_file.read()
    size_bytes = len(data)

    validation_error = validate_upload_file(filename, size_bytes)
    if validation_error:
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.file_failed",
            category="operational",
            source="onboarding.upload",
            payload={"file_name": filename, "reason": validation_error},
        )
        db.commit()
        return {
            "ok": False,
            "error": validation_error,
            "file_name": filename,
            "reply": (
                "Не удалось принять файл. "
                + (
                    "Слишком большой — максимум 20 МБ."
                    if validation_error == "file_too_large"
                    else "Формат не поддерживается. Можно: PDF, DOCX, XLSX, CSV, TXT."
                )
            ),
        }

    upload_id = uuid.uuid4()
    storage_name = f"{upload_id.hex}{_extension(filename)}"
    storage_path = _storage_dir(ctx.tenant_id) / storage_name
    storage_path.write_bytes(data)

    row = OnboardingUpload(
        id=upload_id,
        tenant_id=ctx.tenant_id,
        conversation_id=conversation_id,
        file_name=filename,
        content_type=upload_file.content_type,
        storage_path=str(storage_path),
        size_bytes=size_bytes,
        parse_status="pending",
        meta={"original_filename": upload_file.filename},
    )
    db.add(row)
    db.flush()

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="onboarding.file_uploaded",
        category="operational",
        source="onboarding.upload",
        payload={
            "upload_id": str(upload_id),
            "file_name": filename,
            "size_bytes": size_bytes,
            "conversation_id": str(conversation_id) if conversation_id else None,
        },
    )

    extracted = _extract_via_brain(
        data,
        filename=filename,
        content_type=upload_file.content_type or "",
    )
    text = str(extracted.get("text") or "").strip()
    method = str(extracted.get("method") or "")
    error = str(extracted.get("error") or "")
    reply = _build_feedback(filename, text, method=method, error=error)

    document_id: str | None = None
    parse_status = "parsed"

    if len(text) >= 20:
        title = f"Файл: {filename}"
        body = f"# {title}\n\nИсточник: загруженный файл `{filename}`.\n\n{text}"
        kb = upsert_draft_knowledge(
            db,
            tenant,
            title=title[:255],
            body=body[:50000],
            source=f"onboarding.file:{filename}",
            document_id=f"doc-{tenant.slug}-file-{upload_id.hex[:10]}",
        )
        if kb.get("ok"):
            document_id = str(kb.get("document_id") or "")
            row.extracted_document_id = document_id
            _append_source_to_draft(
                tenant,
                {
                    "type": "file",
                    "file_name": filename,
                    "upload_id": str(upload_id),
                    "document_id": document_id,
                    "method": method,
                },
            )
            emit_event(
                db,
                tenant_id=ctx.tenant_id,
                event_type="onboarding.knowledge_draft_updated",
                category="operational",
                source="onboarding.upload",
                payload={"document_id": document_id, "file_name": filename},
            )
        else:
            parse_status = "kb_failed"
            reply = (
                f"Я прочитал «{filename}», но не смог сохранить в черновик. "
                "Попробуйте ещё раз или опишите содержание текстом."
            )
    else:
        parse_status = "failed" if error else "empty"
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.file_failed",
            category="operational",
            source="onboarding.upload",
            payload={"upload_id": str(upload_id), "file_name": filename, "method": method, "error": error},
        )

    row.parse_status = parse_status
    row.meta = {
        **(row.meta or {}),
        "extract_method": method,
        "extract_error": error,
        "text_chars": len(text),
    }

    if conversation_id:
        db.add(
            Message(
                tenant_id=ctx.tenant_id,
                conversation_id=conversation_id,
                role="user",
                body=f"📎 {filename}",
                meta={"kind": "onboarding_file", "upload_id": str(upload_id), "file_name": filename},
            )
        )
        db.add(
            Message(
                tenant_id=ctx.tenant_id,
                conversation_id=conversation_id,
                role="assistant",
                body=reply,
                meta={
                    "kind": "onboarding_file_feedback",
                    "upload_id": str(upload_id),
                    "document_id": document_id,
                    "parse_status": parse_status,
                },
            )
        )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="onboarding.file_parsed",
        category="operational",
        source="onboarding.upload",
        payload={
            "upload_id": str(upload_id),
            "file_name": filename,
            "parse_status": parse_status,
            "document_id": document_id,
            "method": method,
        },
    )
    db.commit()

    return {
        "ok": True,
        "upload_id": str(upload_id),
        "file_name": filename,
        "size_bytes": size_bytes,
        "parse_status": parse_status,
        "document_id": document_id,
        "extract_method": method,
        "reply": reply,
        "conversation_id": str(conversation_id) if conversation_id else None,
    }


def list_onboarding_uploads(
    db: Session,
    ctx: TenantContext,
    *,
    conversation_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    q = db.query(OnboardingUpload).filter(OnboardingUpload.tenant_id == ctx.tenant_id)
    if conversation_id:
        q = q.filter(OnboardingUpload.conversation_id == conversation_id)
    rows = q.order_by(OnboardingUpload.created_at.desc()).limit(min(limit, 100)).all()
    return [
        {
            "upload_id": str(row.id),
            "file_name": row.file_name,
            "size_bytes": row.size_bytes,
            "parse_status": row.parse_status,
            "document_id": row.extracted_document_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "meta": row.meta or {},
        }
        for row in rows
    ]
