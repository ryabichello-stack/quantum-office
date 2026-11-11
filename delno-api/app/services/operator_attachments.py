"""Hermes/operator chat attachments — images (vision) + text/docs."""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any

MAX_ATTACHMENTS = 4
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_FILE_BYTES = 8 * 1024 * 1024

IMAGE_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

TEXT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/html",
        "application/json",
        "application/xml",
        "text/xml",
    }
)

DOC_EXTENSIONS = frozenset({".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".html", ".htm", ".json"})


def _ext(name: str) -> str:
    lower = (name or "").lower()
    if "." not in lower:
        return ""
    return "." + lower.rsplit(".", 1)[-1]


def _decode_payload(raw: str) -> tuple[bytes, str | None]:
    """Return bytes and optional mime from data-URL or bare base64."""
    value = (raw or "").strip()
    mime = None
    if value.startswith("data:") and "," in value:
        header, b64 = value.split(",", 1)
        m = re.match(r"data:([^;]+)", header)
        if m:
            mime = m.group(1).strip().lower()
        value = b64
    try:
        data = base64.b64decode(value, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("invalid_base64") from exc
    return data, mime


def normalize_attachments(raw_items: list[dict[str, Any]] | None) -> dict[str, Any]:
    """
    Validate client attachments.

    Returns {
      ok, error?, items: [{filename, content_type, kind, size, data_url?, text_excerpt?}],
      vision_parts, text_context, summary_labels
    }
    """
    if not raw_items:
        return {
            "ok": True,
            "items": [],
            "vision_parts": [],
            "text_context": "",
            "summary_labels": [],
        }
    if len(raw_items) > MAX_ATTACHMENTS:
        return {"ok": False, "error": "too_many_attachments", "items": []}

    items: list[dict[str, Any]] = []
    vision_parts: list[dict[str, Any]] = []
    text_chunks: list[str] = []
    labels: list[str] = []

    for raw in raw_items:
        if not isinstance(raw, dict):
            return {"ok": False, "error": "invalid_attachment", "items": []}
        filename = str(raw.get("filename") or "file").strip()[:200] or "file"
        content_type = str(raw.get("content_type") or "application/octet-stream").split(";")[0].strip().lower()
        payload = str(raw.get("data_base64") or raw.get("data_url") or "")
        if not payload:
            return {"ok": False, "error": "empty_attachment", "items": []}
        try:
            data, mime_from_data = _decode_payload(payload)
        except ValueError:
            return {"ok": False, "error": "invalid_base64", "items": []}
        if mime_from_data:
            content_type = mime_from_data
        if content_type == "image/jpg":
            content_type = "image/jpeg"

        ext = _ext(filename)
        is_image = content_type in IMAGE_TYPES or ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        if is_image:
            if len(data) > MAX_IMAGE_BYTES:
                return {"ok": False, "error": "image_too_large", "items": []}
            if content_type not in IMAGE_TYPES:
                # infer from extension
                content_type = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".png": "image/png",
                    ".webp": "image/webp",
                    ".gif": "image/gif",
                }.get(ext, "image/jpeg")
            data_url = f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"
            vision_parts.append({"type": "image_url", "image_url": {"url": data_url}})
            items.append(
                {
                    "filename": filename,
                    "content_type": content_type,
                    "kind": "image",
                    "size": len(data),
                    "data_url": data_url,
                }
            )
            labels.append(f"🖼 {filename}")
            continue

        if len(data) > MAX_FILE_BYTES:
            return {"ok": False, "error": "file_too_large", "items": []}
        if ext and ext not in DOC_EXTENSIONS and content_type not in TEXT_TYPES:
            return {"ok": False, "error": "unsupported_type", "items": []}

        excerpt = ""
        if content_type in TEXT_TYPES or ext in {".txt", ".md", ".csv", ".json", ".html", ".htm"}:
            try:
                excerpt = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                excerpt = ""
        if not excerpt:
            # Best-effort: still try utf-8 for unknown docs; PDF/DOCX need brain later
            try:
                excerpt = data.decode("utf-8", errors="replace")
            except Exception:  # noqa: BLE001
                excerpt = ""
        excerpt = excerpt.strip()
        if len(excerpt) > 12000:
            excerpt = excerpt[:12000] + "\n…[обрезано]"
        if excerpt:
            text_chunks.append(f"--- файл: {filename} ---\n{excerpt}")
        else:
            text_chunks.append(
                f"--- файл: {filename} ({content_type}, {len(data)} байт) ---\n"
                "(бинарный документ: текст не извлечён; опишите, что с ним сделать)"
            )
        items.append(
            {
                "filename": filename,
                "content_type": content_type,
                "kind": "file",
                "size": len(data),
                "text_excerpt": excerpt[:2000] if excerpt else "",
            }
        )
        labels.append(f"📎 {filename}")

    return {
        "ok": True,
        "items": items,
        "vision_parts": vision_parts,
        "text_context": "\n\n".join(text_chunks).strip(),
        "summary_labels": labels,
    }


def build_user_content(message: str, normalized: dict[str, Any]) -> str | list[dict[str, Any]]:
    """OpenAI chat content: plain string or multimodal parts."""
    text = (message or "").strip()
    vision = normalized.get("vision_parts") or []
    file_ctx = (normalized.get("text_context") or "").strip()
    labels = normalized.get("summary_labels") or []

    if not text:
        if vision and not file_ctx:
            text = "Что на этом изображении? Кратко опиши и скажи, чем помочь."
        elif file_ctx:
            text = "Я приложил файл(ы). Посмотри содержимое и скажи, что с ними делать дальше."
        else:
            text = "…"

    if file_ctx:
        text = f"{text}\n\n{file_ctx}"

    if not vision:
        return text

    parts: list[dict[str, Any]] = [{"type": "text", "text": text}]
    parts.extend(vision)
    if labels:
        # keep labels only for logging; already in text if needed
        pass
    return parts
