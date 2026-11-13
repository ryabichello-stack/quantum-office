"""KB draft from owner attachments: images (vision) + PDF/DOCX/text files.

No extra «media setup» — Hermes reads what the owner attaches and co-builds
the commercial profile the same way as site / social / free-text.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.services import hermes_ops
from app.services.hermes_kb_build import build_company_kb_draft


_KB_HINTS = (
    "баз",
    "знани",
    "kb",
    "профиль",
    "компани",
    "в кб",
    "кп",
    "коммерческ",
    "презентац",
    "оферт",
    "прайс",
    "тариф",
    "собери",
    "обогати",
    "из файла",
    "из картин",
    "из фото",
    "из вложен",
)


def _kb_step_open(db: Session, ctx: TenantContext) -> bool:
    try:
        st = hermes_ops.office_setup_status(db, ctx) or {}
        return not bool((st.get("checks") or {}).get("kb", {}).get("ok"))
    except Exception:  # noqa: BLE001
        return True


def wants_kb_from_attachments(message: str, attachments: dict[str, Any] | None) -> bool:
    if not attachments or not (attachments.get("items") or []):
        return False
    low = (message or "").lower()
    if any(h in low for h in _KB_HINTS):
        return True
    # Bare attachment during empty/short message → treat as company material.
    if len((message or "").strip()) < 8:
        return True
    return False


def _vision_extract_commercial(
    *,
    message: str,
    vision_parts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ask a multimodal model to pull commercial facts from image(s)."""
    if not vision_parts:
        return {"ok": False, "text": "", "error": "no_vision"}
    try:
        from app.services.model_provider import get_model_provider

        provider = get_model_provider()
        system = (
            "Ты коммерческий директор. По изображению (КП, презентация, прайс, скрин сайта, "
            "визитка) извлеки факты для базы знаний компании по-русски.\n"
            "Структура: кто мы; продукты/услуги; для кого; цены/условия; процесс; контакты; "
            "FAQ/возражения; пробелы.\n"
            "Только то, что видно. Нет факта — «не найдено». Не выдумывай."
        )
        user_text = (message or "").strip() or (
            "Извлеки коммерческий профиль с этого изображения для базы знаний."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        content.extend(vision_parts[:4])
        completion = provider.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            model="gpt-4o-mini",
            max_tokens=3500,
        )
        if not completion.get("ok"):
            return {"ok": False, "text": "", "error": completion.get("error") or "vision_failed"}
        reply = str(completion["data"]["choices"][0]["message"]["content"]).strip()
        provider_name = str(completion.get("provider") or "")
        if provider_name == "stub" and reply.startswith("[stub]"):
            return {"ok": False, "text": "", "error": "stub_echo"}
        return {"ok": bool(reply), "text": reply, "provider": provider_name}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "text": "", "error": type(exc).__name__}


def try_kb_draft_from_attachments(
    db: Session,
    ctx: TenantContext,
    message: str,
    attachments: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """If attachments look like company materials, build office_loop.kb_draft.

    Returns a reply payload {reply, tool_calls, sources?} or None to fall through.
    """
    if not attachments or not (attachments.get("items") or []):
        return None

    kb_open = _kb_step_open(db, ctx)
    explicit = wants_kb_from_attachments(message, attachments)
    if not kb_open and not explicit:
        return None

    text_ctx = str(attachments.get("text_context") or "").strip()
    vision_parts = list(attachments.get("vision_parts") or [])
    labels = list(attachments.get("summary_labels") or [])
    tool_calls: list[dict[str, Any]] = [
        {
            "tool": "attachments",
            "ok": True,
            "count": len(attachments.get("items") or []),
            "kinds": [i.get("kind") for i in (attachments.get("items") or [])],
            "labels": labels[:4],
        }
    ]

    free_parts: list[str] = []
    if text_ctx:
        free_parts.append(text_ctx)

    vision_note = ""
    if vision_parts:
        extracted = _vision_extract_commercial(message=message, vision_parts=vision_parts)
        tool_calls.append(
            {
                "tool": "vision.extract_commercial",
                "ok": bool(extracted.get("ok")),
                "error": extracted.get("error"),
                "chars": len(extracted.get("text") or ""),
            }
        )
        if extracted.get("ok") and extracted.get("text"):
            free_parts.append(
                "--- распознано с изображения (vision) ---\n" + str(extracted["text"])
            )
        else:
            vision_note = (
                "Картинку увидел, но коммерческий текст с неё снять не удалось "
                f"({extracted.get('error') or 'пусто'}). "
                "Пришлите PDF/DOCX или надиктуйте услуги и цены."
            )

    free_text = "\n\n".join(p for p in free_parts if p).strip()
    if not free_text:
        return {
            "reply": vision_note
            or (
                "Вложение принято, но текста для базы знаний не извлеклось. "
                "Пришлите сайт, PDF/DOCX или опишите услуги текстом."
            ),
            "tool_calls": tool_calls,
            "sources": [],
            "suggested_actions": [
                {"title": "Сайт", "text": "Вот ссылка на наш сайт — собери базу знаний"},
                {"title": "Текстом", "text": "Сейчас расскажу о компании: "},
            ],
        }

    out = build_company_kb_draft(
        db,
        ctx,
        message=message or None,
        free_text=free_text,
        also_search=True,
        research_social=True,
    )
    tool_calls.append(
        {
            "tool": "office.build_kb_draft",
            "ok": bool(out.get("ok")),
            "from_attachments": True,
            "pages_count": out.get("pages_count"),
            "suggested_actions": (out.get("suggested_actions") or [])[:5],
        }
    )
    if not out.get("ok"):
        return {
            "reply": (
                f"Из вложений текст есть ({len(free_text)} символов), но черновик не собрался: "
                f"{out.get('error') or out.get('message') or 'error'}. "
                + (vision_note or "")
            ).strip(),
            "tool_calls": tool_calls,
            "sources": [],
        }

    reply = str(out.get("message") or "").strip()
    if vision_note:
        reply = f"{reply}\n\n_{vision_note}_"
    return {
        "reply": reply,
        "tool_calls": tool_calls,
        "sources": [],
        "suggested_actions": out.get("suggested_actions") or [
            {"title": "Добавить в KB", "text": "Подтверди черновик базы знаний"},
            {"title": "Уточнить цены", "text": "Цены и условия такие: "},
        ],
    }
