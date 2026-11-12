"""Blank onboarding templates for any tenant (company profile + telephony script)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Packaged with API first (works in Docker); then monorepo / prod knowledge tree.
_CANDIDATE_ROOTS = [
    Path(__file__).resolve().parents[1] / "data" / "templates",
    Path(__file__).resolve().parents[3] / "delno-knowledge" / "templates",
    Path("/opt/delno/knowledge/templates"),
    Path("/workspace/delno-knowledge/templates"),
]

TEMPLATES: dict[str, dict[str, str]] = {
    "company-profile": {
        "id": "company-profile",
        "title": "Профиль компании",
        "filename": "company-profile.md",
        "description": "Заполните и загрузите в Знания — Hermes и каналы будут опираться на эти факты.",
        "doc_type": "company_profile",
    },
    "telephony-script": {
        "id": "telephony-script",
        "title": "Сценарий телефонного секретаря",
        "filename": "telephony-script.md",
        "description": "Сценарий входящей линии. Можно заполнить вручную или надиктовать Hermes.",
        "doc_type": "telephony_script",
    },
    "company-profile-sample": {
        "id": "company-profile-sample",
        "title": "Пример: профиль компании",
        "filename": "examples/company-profile.sample.md",
        "description": "Образец заполнения (вымышленная компания).",
        "doc_type": "company_profile",
        "example": "true",
    },
    "telephony-script-sample": {
        "id": "telephony-script-sample",
        "title": "Пример: сценарий секретаря",
        "filename": "examples/telephony-script.sample.md",
        "description": "Образец сценария телефонии.",
        "doc_type": "telephony_script",
        "example": "true",
    },
}


def _templates_root() -> Path | None:
    for root in _CANDIDATE_ROOTS:
        if root.is_dir():
            return root
    return None


def list_templates(*, include_examples: bool = True) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for meta in TEMPLATES.values():
        if meta.get("example") and not include_examples:
            continue
        items.append(
            {
                "id": meta["id"],
                "title": meta["title"],
                "description": meta["description"],
                "doc_type": meta["doc_type"],
                "example": bool(meta.get("example")),
                "filename": Path(meta["filename"]).name,
            }
        )
    return items


def get_template(template_id: str) -> dict[str, Any] | None:
    meta = TEMPLATES.get((template_id or "").strip())
    if not meta:
        return None
    root = _templates_root()
    if not root:
        return None
    path = root / meta["filename"]
    if not path.is_file():
        return None
    body = path.read_text(encoding="utf-8")
    return {
        "id": meta["id"],
        "title": meta["title"],
        "description": meta["description"],
        "doc_type": meta["doc_type"],
        "example": bool(meta.get("example")),
        "filename": Path(meta["filename"]).name,
        "content_type": "text/markdown; charset=utf-8",
        "body": body,
    }
