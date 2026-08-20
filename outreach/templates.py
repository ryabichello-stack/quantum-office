"""Outreach email templates (cooperation / industry packs)."""

from __future__ import annotations

from html import escape

from content.packs import LEGAL_FOOTER_HTML, LEGAL_FOOTER_PLAIN, ensure_legal_footer

_WEAK_NAMES = frozenset(
    {
        "",
        "коллега",
        "тест",
        "test",
        "you",
        "unknown",
        "клиент",
        "contact",
        "name",
        "user",
        "руководитель",
    }
)
_COMPANY_MARKERS = (
    "ооо",
    "оао",
    "зао",
    "пао",
    "ао ",
    " ао",
    "ип ",
    "общество с ограничен",
    "ломбард ",
    " ltd",
    "llc",
    "inc.",
)


def _looks_like_company(name: str) -> bool:
    low = f" {name.lower()} "
    if any(m in low for m in _COMPANY_MARKERS):
        return True
    # Long ALL-CAPS org titles
    letters = [c for c in name if c.isalpha()]
    if len(letters) >= 8 and sum(1 for c in letters if c.isupper()) / len(letters) > 0.85:
        return True
    return False


def resolve_greeting(contact_name: str | None) -> tuple[str, str]:
    """Return (greeting_line, display_name) for personalization.

    Prefer a real person (director) name; otherwise address the руководитель.
    """
    raw = (contact_name or "").strip()
    if (
        not raw
        or raw.lower() in _WEAK_NAMES
        or "@" in raw
        or len(raw) < 2
        or _looks_like_company(raw)
    ):
        return "Уважаемый руководитель, добрый день!", "руководитель"
    # Prefer first name if FIO "Фамилия Имя Отчество"
    parts = raw.replace(",", " ").split()
    if len(parts) >= 2 and all(p[:1].isupper() for p in parts if p):
        # Russian FIO often Surname First Patronymic — greet by first name if 3 parts
        if len(parts) >= 3:
            first = parts[1]
            return f"{first}, добрый день!", first
    return f"{raw}, добрый день!", raw


DEFAULT_PLAIN = """{greeting}

Мы — команда Quantum Labs.

Строим **платёжную инфраструктуру для бизнеса**: выплаты физлицам на карты и по СБП
(Quantum Payouts), приём платежей, эквайринг, API и индивидуальные расчётные сценарии.

Клиент заключает **прямые договоры с банками** — мы не посредник. Мы технологический партнёр:
помогаем **согласовать сильные ставки по рынку**, подключить технологию и сопровождаем в работе.

Готовы за 15 минут сравнить вашу текущую схему с доступными вариантами.

{website}{phone_line}

С уважением,
команда {company}
""" + LEGAL_FOOTER_PLAIN

DEFAULT_HTML = ""  # built from plain via packs helper when empty; keep simple fallback below


def _default_html() -> str:
    from content.packs import _html_from_plain

    return _html_from_plain(
        DEFAULT_PLAIN.replace(LEGAL_FOOTER_PLAIN, "").rstrip()
    ).replace("{legal_html}", LEGAL_FOOTER_HTML)


def _safe_format(template: str, mapping: dict[str, str]) -> str:
    class _Map(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    return template.format_map(_Map(**mapping))


def render_cooperation(
    *,
    contact_name: str,
    company_name: str,
    website: str,
    phone: str,
    unsubscribe_mailto: str,
    unsubscribe_url: str | None = None,
    plain_template: str | None = None,
    html_template: str | None = None,
) -> tuple[str, str]:
    from content.packs import strip_md_bold

    greeting, name = resolve_greeting(contact_name)
    company = company_name.strip() or "Quantum Labs"
    site = website.strip() or "https://quantumlabs.ru"
    unsub = unsubscribe_mailto.strip() or "office@quantumlabs.ru"
    unsub_url = (unsubscribe_url or "").strip() or f"mailto:{unsub}?subject=unsubscribe"
    phone_s = phone.strip()
    phone_line = f"\nТелефон: {phone_s}" if phone_s else ""
    phone_html = f"<p>Телефон: {escape(phone_s)}</p>" if phone_s else ""

    plain_src = (plain_template or "").strip() or DEFAULT_PLAIN
    html_src = (html_template or "").strip()
    if not html_src:
        from content.packs import _html_from_plain

        html_src = _html_from_plain(
            plain_src.replace(LEGAL_FOOTER_PLAIN, "").rstrip()
            if LEGAL_FOOTER_PLAIN in plain_src
            else plain_src
        ).replace("{legal_html}", LEGAL_FOOTER_HTML)

    plain_src, html_src = ensure_legal_footer(plain_src, html_src)

    mapping_plain = {
        "greeting": greeting,
        "name": name,
        "company": company,
        "website": site,
        "unsub": unsub,
        "unsub_url": unsub_url,
        "phone": phone_s,
        "phone_line": phone_line,
        "phone_html": phone_html,
    }
    mapping_html = {
        "greeting": escape(greeting),
        "name": escape(name),
        "company": escape(company),
        "website": escape(site),
        "unsub": escape(unsub),
        "unsub_url": escape(unsub_url),
        "phone": escape(phone_s),
        "phone_line": escape(phone_line),
        "phone_html": phone_html,
    }
    plain = strip_md_bold(_safe_format(plain_src, mapping_plain))
    html = _safe_format(html_src, mapping_html)
    return plain, html
