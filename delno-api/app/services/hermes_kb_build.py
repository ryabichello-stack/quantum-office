"""Deep multi-source company KB build for Hermes onboarding.

Pipeline: deep site crawl → social harvest → open-web enrichment →
structured draft → clarifying questions for the owner (co-build).
Does NOT auto-publish: writes office_loop.kb_draft for confirm.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import web_browser
from app.services.hermes_nous.onboarding import save_kb_draft
from app.services.onboarding_website import extract_url_from_message

_SOCIAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("telegram", re.compile(r"https?://(?:t\.me|telegram\.me)/[A-Za-z0-9_+/.-]+", re.I)),
    ("instagram", re.compile(r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_./-]+", re.I)),
    ("vk", re.compile(r"https?://(?:www\.)?vk\.(?:com|me)/[A-Za-z0-9_./-]+", re.I)),
    ("max", re.compile(r"https?://(?:web\.)?max\.ru/[A-Za-z0-9_./-]+", re.I)),
    ("youtube", re.compile(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[A-Za-z0-9_?=&./-]+", re.I)),
)

_DEFAULT_KB_PATHS = (
    "/about",
    "/o-nas",
    "/onas",
    "/company",
    "/contacts",
    "/kontakt",
    "/kontakty",
    "/uslugi",
    "/services",
    "/products",
    "/pricing",
    "/price",
    "/ceny",
    "/tarif",
    "/tarify",
    "/faq",
    "/blog",
    "/news",
    "/offer",
    "/oferta",
)

_GAP_MARKERS = (
    ("hours", ("час", "график", "режим работы", "пн-", "пн–", "будн")),
    ("pricing", ("цен", "прайс", "тариф", "стоимость", "руб", "₽")),
    ("audience", ("для кого", "клиент", "аудитор", "сегмент", "b2b", "b2c")),
    ("usp", ("отлича", "преимущ", "почему мы", "уникальн")),
    ("geo", ("город", "москв", "регион", "офис", "адрес")),
)


def extract_social_urls(text: str) -> dict[str, list[str]]:
    """Pull public social / messenger URLs from dossier or page text."""
    found: dict[str, list[str]] = {}
    blob = text or ""
    for kind, pattern in _SOCIAL_PATTERNS:
        hits: list[str] = []
        seen: set[str] = set()
        for match in pattern.finditer(blob):
            url = match.group(0).rstrip(".,;:!?)\"'")
            key = url.rstrip("/").lower()
            if key in seen:
                continue
            seen.add(key)
            hits.append(url)
        if hits:
            found[kind] = hits[:5]
    return found


def _normalize_url_list(urls: list[str] | None, message: str | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    candidates = list(urls or [])
    if message:
        extracted = extract_url_from_message(message)
        if extracted:
            candidates.insert(0, extracted)
        for raw in web_browser.extract_urls(message):
            candidates.append(raw)
    for raw in candidates:
        u = (raw or "").strip()
        if not u:
            continue
        if not u.startswith(("http://", "https://")):
            if "." in u and " " not in u:
                u = f"https://{u}"
            else:
                continue
        key = u.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def _company_label(db: Session, ctx: TenantContext, seed_url: str | None, free_text: str) -> str:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    name = (tenant.name or "").strip()
    if name and name.lower() not in {"demo", "tenant", "office"}:
        return name[:120]
    if seed_url:
        host = (urlparse(seed_url).hostname or "").removeprefix("www.")
        if host:
            return host.split(".")[0][:80]
    first = (free_text or "").strip().split("\n", 1)[0]
    return (first[:80] or "компании").strip()


def _detect_gaps(blob: str) -> list[str]:
    low = (blob or "").lower()
    gaps: list[str] = []
    labels = {
        "hours": "график работы / часы",
        "pricing": "цены / тарифы",
        "audience": "для кого продукт (аудитория)",
        "usp": "чем отличаетесь от конкурентов",
        "geo": "география / адрес",
    }
    for key, markers in _GAP_MARKERS:
        if not any(m in low for m in markers):
            gaps.append(labels[key])
    return gaps


def _followup_questions(
    *,
    social_found: dict[str, list[str]],
    gaps: list[str],
    pages_count: int,
) -> list[str]:
    qs: list[str] = []
    missing_social = [
        label
        for kind, label in (
            ("telegram", "Telegram-канал или бот"),
            ("instagram", "Instagram"),
            ("vk", "ВКонтакте"),
            ("max", "MAX"),
        )
        if kind not in social_found
    ]
    if missing_social:
        qs.append(
            "Есть ли ещё публичные каналы, которых нет в черновике: "
            + ", ".join(missing_social)
            + "? Пришлите ссылки — дособеру оттуда."
        )
    for gap in gaps[:3]:
        qs.append(f"Уточните, пожалуйста: {gap} — этого не хватает в открытых источниках.")
    if pages_count < 3:
        qs.append(
            "На сайте мало внутренних страниц в открытом доступе. "
            "Есть ли каталог услуг, прайс или PDF, который можно добавить?"
        )
    qs.append(
        "Проверьте черновик базы знаний: что поправить, что добавить от себя "
        "(тон общения, запреты, типичные возражения клиентов)?"
    )
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in qs:
        if q in seen:
            continue
        seen.add(q)
        out.append(q)
    return out[:6]


_COMMERCIAL_KB_SYSTEM = (
    "Ты — коммерческий директор компании. По досье сайта, соцсетей и открытого веба "
    "собери максимально сильное коммерческое описание компании для секретаря и продаж "
    "(markdown, русский). Формулируй уверенно и продающе, но только на фактах из материалов — "
    "не выдумывай цены, SLA, юрлицо, кейсы. Нет факта — «не найдено в источниках» + в пробелы.\n"
    "Обязательные секции (все):\n"
    "# {company} — коммерческий профиль\n"
    "## 1. Кто мы (1–3 сильных предложения + юрлицо/ИНН если есть)\n"
    "## 2. Продукты и услуги (каждая: что / для кого / результат / цена или «по запросу» / срок/SLA)\n"
    "## 3. Для кого (ICP, сегменты, объёмы, отрасли)\n"
    "## 4. Цены и условия (комиссии, пороги, тарифы, договор/оферта, ограничения)\n"
    "## 5. Как работает сервис (шаги клиента: заявка → … → отчётность)\n"
    "## 6. Особенности и преимущества (факты, сильные формулировки)\n"
    "## 7. Интеграции и каналы (ЛК, API, 1С, банки, соцсети)\n"
    "## 8. Контакты\n"
    "## 9. FAQ (вопрос → короткий ответ; только из источников)\n"
    "## 10. Возражения и безопасные формулировки (если есть факты)\n"
    "## 11. Тон и запреты\n"
    "## 12. Пробелы — что уточнить у владельца\n"
    "Пиши плотно, списками. Без воды и без «если нужно могу…»."
)


def _synthesize_markdown(
    *,
    company: str,
    dossier: str,
    free_text: str,
    social_found: dict[str, list[str]],
    source_urls: list[str],
    search_bits: str,
    gaps: list[str],
) -> dict[str, str]:
    """LLM-structured commercial KB; deterministic fallback if model unavailable."""
    system = _COMMERCIAL_KB_SYSTEM.replace("{company}", company or "Компания")
    user_parts = [
        f"Компания (ярлык): {company}",
        f"Исходные URL: {', '.join(source_urls) or '—'}",
    ]
    if free_text.strip():
        user_parts.append(f"Текст от владельца:\n{free_text.strip()[:6000]}")
    if social_found:
        bits = "; ".join(f"{k}: {', '.join(v)}" for k, v in social_found.items())
        user_parts.append(f"Найденные соцсети/мессенджеры: {bits}")
    if search_bits.strip():
        user_parts.append(f"Доп. из открытого веба:\n{search_bits.strip()[:8000]}")
    if gaps:
        user_parts.append("Подозрительные пробелы: " + "; ".join(gaps))
    user_parts.append(f"Досье страниц:\n{dossier[:28000]}")
    user = "\n\n".join(user_parts)

    try:
        from app.services.model_provider import get_model_provider

        provider = get_model_provider()
        out = provider.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=3500,
        )
        if out.get("ok"):
            data = out.get("data") if isinstance(out.get("data"), dict) else out
            text = ""
            try:
                text = str(data["choices"][0]["message"]["content"] or "")
            except Exception:  # noqa: BLE001
                text = str(out.get("reply") or out.get("content") or "")
            text = (text or "").strip()
            if len(text) >= 120:
                title = f"{company} — коммерческий профиль (черновик)"
                return {"title": title[:200], "body": text[:48000]}
    except Exception:  # noqa: BLE001
        pass

    # Deterministic fallback — same commercial skeleton
    lines = [
        f"# {company} — коммерческий профиль",
        "",
        "## 1. Кто мы",
        (free_text.strip()[:1500] if free_text.strip() else "не найдено в источниках"),
        "",
        "## 2. Продукты и услуги",
        "не найдено в источниках — разобрать досье ниже",
        "",
        "## 3. Для кого",
        "не найдено в источниках",
        "",
        "## 4. Цены и условия",
        "не найдено в источниках",
        "",
        "## 5. Как работает сервис",
        "не найдено в источниках",
        "",
        "## 6. Особенности и преимущества",
        "не найдено в источниках",
        "",
        "## 7. Интеграции и каналы",
    ]
    if social_found:
        for kind, urls in social_found.items():
            for u in urls:
                lines.append(f"- {kind}: {u}")
    else:
        lines.append("не найдено в источниках")
    lines.extend(
        [
            "",
            "## 8. Контакты",
            "не найдено в источниках",
            "",
            "## 9. FAQ",
            "не найдено в источниках",
            "",
            "## 10. Возражения и безопасные формулировки",
            "не найдено в источниках",
            "",
            "## 11. Тон и запреты",
            "не найдено в источниках",
            "",
            "## 12. Пробелы — что уточнить у владельца",
        ]
    )
    if gaps:
        lines.extend(f"- {g}" for g in gaps)
    else:
        lines.append("- уточнить услуги, цены, ICP")
    lines.extend(["", "## Источники"])
    lines.extend(f"- {u}" for u in source_urls[:12])
    lines.extend(
        [
            "",
            "## Сырьё с сайта и веба",
            (dossier or search_bits or "—")[:12000],
        ]
    )
    body = "\n".join(lines).strip()
    return {"title": f"{company} — коммерческий профиль (черновик)"[:200], "body": body[:48000]}


def build_company_kb_draft(
    db: Session,
    ctx: TenantContext,
    *,
    urls: list[str] | None = None,
    message: str | None = None,
    free_text: str | None = None,
    max_pages: int = 10,
    also_search: bool = True,
    research_social: bool = True,
) -> dict[str, Any]:
    """Deep multi-source research → structured KB draft + owner questions."""
    url_list = _normalize_url_list(urls, message)
    owner_text = (free_text or "").strip()
    if not url_list and not owner_text:
        return {
            "ok": False,
            "error": "need_url_or_text",
            "message": (
                "Пришлите ссылку на сайт компании (и по возможности Telegram / Instagram / VK) "
                "или текст «кто мы / услуги / для кого» — соберу черновик базы знаний."
            ),
        }

    tool_trace: list[dict[str, Any]] = []
    dossier_parts: list[str] = []
    all_pages: list[dict[str, Any]] = []
    social_found: dict[str, list[str]] = {}
    search_bits_parts: list[str] = []
    primary = url_list[0] if url_list else None
    company = _company_label(db, ctx, primary, owner_text)

    # 1) Deep crawl each seed URL (site + already-known socials).
    for seed in url_list[:6]:
        researched = web_browser.research_site(
            seed,
            max_pages=max_pages if not web_browser.is_social_url(seed) else min(3, max_pages),
            also_search=also_search and not web_browser.is_social_url(seed),
            extra_paths=_DEFAULT_KB_PATHS if not web_browser.is_social_url(seed) else (),
        )
        tool_trace.extend(researched.get("tool_trace") or [])
        if researched.get("dossier"):
            dossier_parts.append(str(researched["dossier"]))
        for page in researched.get("pages") or []:
            if isinstance(page, dict):
                all_pages.append(page)
        # Socials mentioned in this dossier
        blob = str(researched.get("dossier") or "")
        for kind, hits in extract_social_urls(blob).items():
            social_found.setdefault(kind, [])
            for u in hits:
                if u not in social_found[kind]:
                    social_found[kind].append(u)
        for item in researched.get("search_items") or []:
            if isinstance(item, dict):
                search_bits_parts.append(
                    f"- {item.get('title') or ''}: {item.get('url') or ''} — {item.get('snippet') or ''}"
                )

    # 2) Harvest social URLs found on the site (if not already seeds).
    if research_social:
        social_seeds: list[str] = []
        for hits in social_found.values():
            social_seeds.extend(hits)
        known = {u.rstrip("/").lower() for u in url_list}
        for social_url in social_seeds[:6]:
            key = social_url.rstrip("/").lower()
            if key in known:
                continue
            known.add(key)
            researched = web_browser.research_site(
                social_url,
                max_pages=2,
                also_search=False,
            )
            tool_trace.extend(researched.get("tool_trace") or [])
            if researched.get("dossier"):
                dossier_parts.append(str(researched["dossier"]))
            for page in researched.get("pages") or []:
                if isinstance(page, dict):
                    all_pages.append(page)

    # 3) Open-web enrichment by company profile (name + host).
    if also_search and company:
        host = ""
        if primary:
            host = (urlparse(primary).hostname or "").removeprefix("www.")
        queries = [
            f"{company} официальный сайт услуги контакты",
            f"{company} отзывы",
        ]
        if host and host not in company:
            queries.append(f"{host} {company}")
        for q in queries[:2]:
            searched = web_browser.search_web(q, limit=5)
            tool_trace.append(
                {
                    "tool": "web.search",
                    "ok": bool(searched.get("ok")),
                    "query": q,
                    "count": len(searched.get("items") or []),
                }
            )
            for item in (searched.get("items") or [])[:2]:
                if not isinstance(item, dict):
                    continue
                u = str(item.get("url") or "")
                search_bits_parts.append(
                    f"- {item.get('title') or ''}: {u} — {item.get('snippet') or ''}"
                )
                if not u or web_browser.is_social_url(u):
                    # Still try socials from SERP
                    if u and web_browser.is_social_url(u):
                        for kind, hits in extract_social_urls(u).items():
                            social_found.setdefault(kind, [])
                            for h in hits:
                                if h not in social_found[kind]:
                                    social_found[kind].append(h)
                    continue
                page = web_browser.fetch_url(u, max_chars=4500)
                tool_trace.append(
                    {
                        "tool": "web.fetch",
                        "ok": bool(page.get("ok")),
                        "url": page.get("url") or u,
                        "title": page.get("title") or item.get("title") or "",
                        "chars": page.get("chars") or 0,
                    }
                )
                if page.get("ok") and (page.get("chars") or 0) >= 80:
                    dossier_parts.append(
                        f"### Веб: {page.get('title') or u}\nURL: {page.get('url')}\n"
                        f"{(page.get('text') or '')[:4500]}"
                    )
                    all_pages.append(
                        {
                            "url": page.get("url"),
                            "title": page.get("title"),
                            "chars": page.get("chars"),
                            "engine": page.get("engine"),
                        }
                    )
                    for kind, hits in extract_social_urls(str(page.get("text") or "")).items():
                        social_found.setdefault(kind, [])
                        for h in hits:
                            if h not in social_found[kind]:
                                social_found[kind].append(h)

    dossier = "\n\n".join(p for p in dossier_parts if p).strip()
    search_bits = "\n".join(search_bits_parts)[:12000]
    combined = f"{dossier}\n{search_bits}\n{owner_text}"
    gaps = _detect_gaps(combined)
    synthesized = _synthesize_markdown(
        company=company,
        dossier=dossier or owner_text,
        free_text=owner_text,
        social_found=social_found,
        source_urls=url_list,
        search_bits=search_bits,
        gaps=gaps,
    )
    questions = _followup_questions(
        social_found=social_found,
        gaps=gaps,
        pages_count=len(all_pages),
    )

    draft_save = save_kb_draft(
        db,
        ctx,
        title=synthesized["title"],
        body=synthesized["body"],
        source_url=primary,
    )
    if not draft_save.get("ok"):
        return {
            "ok": False,
            "error": "draft_save_failed",
            "message": "Не удалось сохранить черновик KB.",
            "tool_trace": tool_trace,
        }

    pages_label = " · ".join(
        str(p.get("title") or p.get("url") or "") for p in all_pages[:5] if isinstance(p, dict)
    )
    social_label = ""
    if social_found:
        social_label = "; ".join(f"{k}: {len(v)}" for k, v in social_found.items())

    # Show the commercial draft in chat (owner must see structure, not a confirm stub).
    preview = synthesized["body"]
    if len(preview) > 4500:
        preview = preview[:4500].rstrip() + "\n\n… (полный черновик сохранён в кабинете)"

    lines = [
        f"Собрал коммерческий черновик KB для «{company}» "
        f"({len(all_pages)} стр., ~{len(synthesized['body'])} символов).",
    ]
    if pages_label:
        lines.append(f"Источники: {pages_label}")
    if social_label:
        lines.append(f"Нашёл каналы: {social_label}")
    else:
        lines.append("Публичные Telegram / Instagram / VK на сайте не нашёл.")
    lines.append(
        "Это черновик для коммерческой работы (услуги / ICP / цены / условия / FAQ). "
        "Пока не публикую в боевую KB — проверьте и подтвердите."
    )
    lines.append("")
    lines.append(preview)
    lines.append("")
    lines.append("Дальше уточним вместе:")
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")

    return {
        "ok": True,
        "title": synthesized["title"],
        "body": synthesized["body"],
        "chars": len(synthesized["body"]),
        "pages": all_pages,
        "pages_count": len(all_pages),
        "social_found": social_found,
        "gaps": gaps,
        "questions": questions,
        "source_url": primary,
        "kb_draft": draft_save.get("kb_draft"),
        "loop": draft_save.get("loop"),
        "tool_trace": tool_trace,
        "message": "\n".join(lines),
        "suggested_actions": [
            {"title": "Подтвердить KB", "text": "Подтверди черновик базы знаний"},
            {"title": "Уточнить цены", "text": "Цены и условия такие: "},
            {"title": "Добавить каналы", "text": "Вот ссылки на Telegram / Instagram / VK: "},
        ],
    }
