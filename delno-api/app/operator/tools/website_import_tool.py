"""Hermes: import company website into tenant KB + propose connector setup."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services import hermes_ops
from app.services.instant_demo import import_website_to_tenant
from app.services.onboarding_website import extract_url_from_message


class OfficeImportWebsiteTool:
    name = "office.import_website"
    description = (
        "Fetch a company website, put structured text into the tenant knowledge base, "
        "and return next steps to finish office connectors (mail, telegram, phone, …)."
    )
    # Explicit owner request ("зайди на сайт…") is consent; run immediately.
    critical_write = False
    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Website URL or domain, e.g. https://quantumpayouts.ru",
            },
            "message": {
                "type": "string",
                "description": "Optional free text that may contain the URL",
            },
        },
        "required": [],
    }

    def run(self, db: Session, ctx: TenantContext, **params: Any) -> ToolResult:
        raw = str(params.get("url") or params.get("message") or "").strip()
        url = extract_url_from_message(raw) or (raw if raw.startswith("http") else None)
        if not url and raw and "." in raw and " " not in raw:
            url = raw
        if not url:
            return ToolResult(ok=False, message="Нужен URL сайта, например https://quantumpayouts.ru")

        try:
            result = import_website_to_tenant(
                db,
                ctx,
                website_url=url,
                source="hermes.import_website",
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, message=f"Не удалось скачать сайт: {exc}")

        title = result.get("title") or "сайт"
        url = result.get("url") or url
        kb_ok = bool(result.get("kb_ok") or result.get("ok"))
        chars = int(result.get("chars") or 0)
        paras = int(result.get("paragraph_count") or 0)
        excerpt = str(result.get("excerpt") or "").strip()
        description = str(result.get("description") or "").strip()
        headings = [str(h) for h in (result.get("headings") or []) if str(h).strip()][:5]

        if not kb_ok and not excerpt and not title:
            return ToolResult(
                ok=False,
                data=result,
                message=f"Не удалось разобрать {url}: пустой ответ или KB отклонил документ.",
            )

        setup = hermes_ops.office_setup_status(db, ctx)
        next_steps = setup.get("next_steps") or []
        suggested = _suggested_actions(next_steps)
        # Prefer evidence chips after import
        suggested = [
            {"title": "Что в знаниях", "text": "Покажи, что сейчас в базе знаний про компанию"},
            {"title": "Сценарий", "text": "Предложи сценарий из базы знаний"},
        ] + [a for a in suggested if a.get("title") not in ("База знаний", "Сценарий")]
        suggested = suggested[:5]

        lines: list[str] = []
        if kb_ok:
            lines.append(
                f"Зашёл на {url}: снял «{title}» "
                f"({paras} абзацев, ~{chars} символов) и положил в знания "
                f"(doc `{result.get('document_id') or '—'}`)."
            )
        else:
            lines.append(
                f"Зашёл на {url} («{title}»), но в brain/KB документ не сохранился "
                f"({(result.get('kb') or {}).get('error') or (result.get('kb') or {}).get('reason') or 'kb_failed'}). "
                "Текст ниже — что успел прочитать; повторим запись или загрузите MD вручную."
            )
        if description:
            lines.append(f"О сайте: {description[:280]}")
        if headings:
            lines.append("Заголовки: " + "; ".join(headings))
        if excerpt:
            lines.append("Выдержка:")
            for chunk in excerpt.split("\n"):
                chunk = chunk.strip()
                if chunk:
                    lines.append(f"• {chunk[:220]}")
        else:
            lines.append("На главной мало связного текста — имеет смысл дать ещё страницу услуг/о компании.")

        nxt = next_steps[0] if next_steps else None
        if nxt:
            lines.append(
                f"Обратная связь принята. Следующий логичный шаг: {nxt.get('title')} — {nxt.get('hint')}"
            )
        else:
            lines.append("Могу предложить сценарий секретаря из этих знаний или проверить здоровье офиса.")

        return ToolResult(
            ok=kb_ok or bool(excerpt or title),
            data={
                **result,
                "setup": setup,
                "suggested_actions": suggested,
            },
            message="\n".join(lines),
        )


def _suggested_actions(next_steps: list[dict[str, Any]]) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for step in next_steps[:4]:
        check = str(step.get("check") or "")
        title = str(step.get("title") or "Шаг")
        if check == "phone":
            actions.append({"title": "Телефон", "text": "Настрой телефон секретаря"})
        elif check in {"telegram", "max", "channels"}:
            actions.append({"title": "Каналы", "text": "Что ещё настроить в каналах?"})
        elif check in {"mail", "calendar", "files", "conference", "connectors"}:
            actions.append({"title": title[:40], "text": f"Покажи статус коннекторов и что подключить дальше"})
        elif check == "kb":
            actions.append({"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"})
        else:
            hint = str(step.get("hint") or title)
            actions.append({"title": title[:40], "text": hint[:120]})
    if not actions:
        actions = [
            {"title": "Здоровье", "text": "Проверь здоровье офиса"},
            {"title": "Сетап", "text": "Что ещё настроить в офисе?"},
            {"title": "База знаний", "text": "Покажи, что сейчас в базе знаний"},
        ]
    # always offer health after import
    if not any(a["title"] == "Здоровье" for a in actions):
        actions.append({"title": "Здоровье", "text": "Проверь здоровье офиса"})
    return actions[:5]
