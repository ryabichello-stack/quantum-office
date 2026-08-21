"""Outreach email templates (cooperation / industry packs)."""

from __future__ import annotations

import os
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


DEFAULT_SIGNATURE = """С уважением,
команда Quantum Labs
{company}
{website}
{phone_line}"""


def public_base_url(settings_get=None) -> str:
    base = ""
    if callable(settings_get):
        try:
            base = (settings_get("TRACKING_PUBLIC_BASE") or "").strip()
        except Exception:  # noqa: BLE001
            base = ""
    base = base or (os.getenv("TRACKING_PUBLIC_BASE") or "").strip()
    return (base or "https://a.47z.ru/_ava_outreach").rstrip("/")


def default_logo_url(settings_get=None) -> str:
    return f"{public_base_url(settings_get)}/assets/brand/logo-mark.png"


DEFAULT_PLAIN = """{greeting}

Мы — команда Quantum Labs.

Строим **платёжную инфраструктуру для бизнеса**: выплаты физлицам на карты и по СБП
(Quantum Payouts), приём платежей, эквайринг, API и индивидуальные расчётные сценарии.

Клиент заключает **прямые договоры с банками** — мы не посредник. Мы технологический партнёр:
помогаем **согласовать сильные ставки по рынку**, подключить технологию и сопровождаем в работе.

Готовы за 15 минут сравнить вашу текущую схему с доступными вариантами.

{signature}
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


def clean_blank_lines(text: str) -> str:
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            if out and out[-1] == "":
                continue
            out.append("")
        else:
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out)


def build_signature(
    *,
    signature_template: str | None,
    company: str,
    website: str,
    phone: str,
) -> str:
    """Render editable signature; empty phone/company lines are dropped."""
    phone_s = (phone or "").strip()
    phone_line = f"Телефон: {phone_s}" if phone_s else ""
    tpl = (signature_template or "").strip() or DEFAULT_SIGNATURE
    raw = _safe_format(
        tpl,
        {
            "company": (company or "").strip(),
            "website": (website or "").strip(),
            "phone": phone_s,
            "phone_line": phone_line,
        },
    )
    return clean_blank_lines(raw)


def build_logo_header(*, logo_url: str, company: str) -> str:
    url = (logo_url or "").strip()
    if not url:
        return ""
    label = escape((company or "").strip() or "Quantum Labs")
    return (
        '<div style="margin:0 0 18px;padding:0 0 14px;border-bottom:1px solid #e8e4df">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        '<td style="vertical-align:middle;padding-right:10px">'
        f'<img src="{escape(url, quote=True)}" width="32" height="32" alt="" '
        'style="display:block;border:0;border-radius:7px"/>'
        "</td>"
        '<td style="vertical-align:middle;font-family:Manrope,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:13px;letter-spacing:0.06em;color:#c4470f;font-weight:600">'
        f"{label}</td>"
        "</tr></table></div>\n"
    )


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
    signature_template: str | None = None,
    logo_url: str | None = None,
    logo_enabled: bool = True,
) -> tuple[str, str]:
    from content.packs import strip_md_bold

    greeting, name = resolve_greeting(contact_name)
    company = company_name.strip() or "Quantum Labs"
    site = website.strip() or "https://quantumlabs.ru"
    unsub = unsubscribe_mailto.strip() or "office@quantumlabs.ru"
    unsub_url = (unsubscribe_url or "").strip() or f"mailto:{unsub}?subject=unsubscribe"
    phone_s = phone.strip()
    phone_line = f"\nТелефон: {phone_s}" if phone_s else ""
    phone_html = f"<br>Телефон: {escape(phone_s)}" if phone_s else ""

    signature = build_signature(
        signature_template=signature_template,
        company=company,
        website=site,
        phone=phone_s,
    )
    signature_html = (
        "<p style='margin:1.15em 0 0.35em;line-height:1.5'>"
        + escape(signature).replace("\n", "<br>\n")
        + "</p>"
    )
    logo_header = (
        build_logo_header(logo_url=logo_url or "", company=company) if logo_enabled else ""
    )

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

    # Legacy templates without {signature} still use {website}{phone_line} at the end.
    if "{signature}" not in plain_src and "{phone_line}" not in plain_src and phone_s:
        if site and site in plain_src and "Телефон:" not in plain_src:
            plain_src = plain_src.replace(site, site + phone_line, 1)

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
        "signature": signature,
        "logo_header": "",
    }
    mapping_html = {
        "greeting": escape(greeting),
        "name": escape(name),
        "company": escape(company),
        "website": escape(site),
        "unsub": escape(unsub),
        "unsub_url": escape(unsub_url),
        "phone": escape(phone_s),
        "phone_line": phone_html,
        "phone_html": phone_html,
        "signature": signature_html,
        "logo_header": logo_header,
    }
    plain = strip_md_bold(_safe_format(plain_src, mapping_plain))
    html = _safe_format(html_src, mapping_html)
    if logo_header and "{logo_header}" not in (html_template or "") and logo_header not in html:
        # Inject micro-logo near the top of <body> when template predates the placeholder.
        lower = html.lower()
        idx = lower.find("<body")
        if idx >= 0:
            gt = html.find(">", idx)
            if gt >= 0:
                html = html[: gt + 1] + "\n" + logo_header + html[gt + 1 :]
    return plain, html
