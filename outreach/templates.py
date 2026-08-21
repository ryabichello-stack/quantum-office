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
{company}"""

# Contact lines (website / email / phone) always come from Campaign fields,
# not from the signature textarea — so the user edits them once.


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


def icon_url(name: str, settings_get=None) -> str:
    return f"{public_base_url(settings_get)}/assets/brand/icons/{name}.png"


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


def normalize_signature_template(template: str | None) -> str:
    """Keep closing text only; strip contact placeholders / duplicated contact lines."""
    raw = (template or "").replace("\r\n", "\n")
    drop_exact = {
        "{website}",
        "{email}",
        "{email_line}",
        "{phone}",
        "{phone_line}",
        "{website}{phone_line}",
        "{website}{email_line}",
        "{website}{email_line}{phone_line}",
    }
    out: list[str] = []
    for ln in raw.split("\n"):
        s = ln.strip()
        if s.lower() in {x.lower() for x in drop_exact}:
            continue
        if s.startswith("{") and s.endswith("}") and any(
            k in s for k in ("website", "email", "phone")
        ):
            continue
        out.append(ln.rstrip())
    cleaned = clean_blank_lines("\n".join(out))
    return cleaned or DEFAULT_SIGNATURE


def build_signature(
    *,
    signature_template: str | None,
    company: str,
    website: str,
    phone: str,
    email: str = "",
) -> str:
    """Closing text from template + contacts from dedicated fields (single source)."""
    phone_s = (phone or "").strip()
    email_s = (email or "").strip()
    site = (website or "").strip()
    company_s = (company or "").strip()
    tpl = normalize_signature_template(signature_template)
    text = clean_blank_lines(
        _safe_format(
            tpl,
            {
                "company": company_s,
                # legacy placeholders → empty (contacts appended below from fields)
                "website": "",
                "phone": "",
                "phone_line": "",
                "email": "",
                "email_line": "",
            },
        )
    )
    contacts: list[str] = []
    if site:
        contacts.append(site)
    if email_s:
        contacts.append(email_s)
    if phone_s:
        contacts.append(f"Телефон: {phone_s}")
    if contacts:
        text = clean_blank_lines(text + "\n" + "\n".join(contacts))
    return text


def _icon_row(*, icon_src: str, label: str, href: str | None = None) -> str:
    safe_label = escape(label)
    content = (
        f'<a href="{escape(href, quote=True)}" '
        'style="color:#0f1b24;text-decoration:none;border:none;outline:none">'
        f"{safe_label}</a>"
        if href
        else f'<span style="color:#0f1b24">{safe_label}</span>'
    )
    return (
        '<div style="margin:0 0 5px;padding:0;border:none;line-height:1.35;'
        "font-size:13px;font-family:Manrope,Segoe UI,Helvetica,Arial,sans-serif\">"
        f'<img src="{escape(icon_src, quote=True)}" width="16" height="16" alt="" '
        'style="display:inline-block;vertical-align:middle;border:0;outline:none;'
        'margin:0 8px 0 0"/>'
        f'<span style="vertical-align:middle;border:none">{content}</span>'
        "</div>"
    )


def build_signature_html(
    *,
    signature_plain: str,
    website: str,
    phone: str,
    email: str,
    icon_base: str | None = None,
    settings_get=None,
) -> str:
    """HTML signature: text + icon contacts from fields (no divider lines)."""
    site = (website or "").strip()
    phone_s = (phone or "").strip()
    email_s = (email or "").strip()
    base = (icon_base or "").rstrip("/") or public_base_url(settings_get)
    web_icon = f"{base}/assets/brand/icons/web.png"
    mail_icon = f"{base}/assets/brand/icons/mail.png"
    phone_icon = f"{base}/assets/brand/icons/phone.png"

    site_host = site
    if site_host.startswith("https://"):
        site_host = site_host[8:]
    elif site_host.startswith("http://"):
        site_host = site_host[7:]
    site_host = site_host.rstrip("/")

    contact_keys = {
        site.lower(),
        site_host.lower(),
        f"https://{site_host}".lower(),
        f"http://{site_host}".lower(),
        phone_s.lower(),
        f"телефон: {phone_s}".lower() if phone_s else "",
        email_s.lower(),
        f"email: {email_s}".lower() if email_s else "",
        f"e-mail: {email_s}".lower() if email_s else "",
        f"почта: {email_s}".lower() if email_s else "",
    }
    contact_keys.discard("")

    text_lines: list[str] = []
    for ln in (signature_plain or "").splitlines():
        key = ln.strip().lower()
        if key in contact_keys:
            continue
        if phone_s and key.startswith("телефон:") and phone_s.lower() in key:
            continue
        if email_s and email_s.lower() in key and ("@" in key):
            continue
        if site_host and key in {site_host.lower(), site.lower()}:
            continue
        text_lines.append(ln)

    text_block = clean_blank_lines("\n".join(text_lines))
    parts: list[str] = []
    if text_block:
        parts.append(
            "<div style='margin:0 0 10px;padding:0;border:none;line-height:1.5;color:#0f1b24;"
            "font-family:Manrope,Segoe UI,Helvetica,Arial,sans-serif;font-size:14px'>"
            + escape(text_block).replace("\n", "<br>\n")
            + "</div>"
        )

    rows: list[str] = []
    if site:
        href = site if "://" in site else f"https://{site}"
        rows.append(_icon_row(icon_src=web_icon, label=site_host or site, href=href))
    if email_s:
        rows.append(
            _icon_row(icon_src=mail_icon, label=email_s, href=f"mailto:{email_s}")
        )
    if phone_s:
        tel = "tel:" + "".join(ch for ch in phone_s if ch.isdigit() or ch == "+")
        rows.append(_icon_row(icon_src=phone_icon, label=phone_s, href=tel or None))

    if rows:
        parts.append(
            '<div style="margin:0;padding:0;border:none">' + "".join(rows) + "</div>"
        )

    if not parts:
        return ""
    return (
        "<div style='margin:1.15em 0 0.35em;padding:0;border:none'>"
        + "".join(parts)
        + "</div>"
    )

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
    contact_email: str | None = None,
    icon_base_url: str | None = None,
    callback_url: str | None = None,
    callback_cta_html: str | None = None,
    callback_cta_plain: str | None = None,
) -> tuple[str, str]:
    from content.packs import strip_md_bold

    greeting, name = resolve_greeting(contact_name)
    company = company_name.strip() or "Quantum Labs"
    site = website.strip() or "https://quantumlabs.ru"
    unsub = unsubscribe_mailto.strip() or "office@quantumlabs.ru"
    unsub_url = (unsubscribe_url or "").strip() or f"mailto:{unsub}?subject=unsubscribe"
    phone_s = phone.strip()
    email_s = (contact_email or "").strip() or unsub
    phone_line = f"\nТелефон: {phone_s}" if phone_s else ""
    phone_html = f"<br>Телефон: {escape(phone_s)}" if phone_s else ""
    email_line = email_s
    cb_url = (callback_url or "").strip()
    cb_html = (callback_cta_html or "").strip()
    cb_plain = (callback_cta_plain or "").strip()
    if cb_url and not cb_html:
        from callback_cta import build_callback_cta_html

        cb_html = build_callback_cta_html(url=cb_url)
    if cb_url and not cb_plain:
        from callback_cta import build_callback_cta_plain

        cb_plain = build_callback_cta_plain(url=cb_url)

    signature = build_signature(
        signature_template=signature_template,
        company=company,
        website=site,
        phone=phone_s,
        email=email_s,
    )
    signature_html = build_signature_html(
        signature_plain=signature,
        website=site,
        phone=phone_s,
        email=email_s,
        icon_base=icon_base_url,
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
        "email": email_s,
        "email_line": email_line,
        "signature": signature,
        "logo_header": "",
        "callback_url": cb_url,
        "callback_cta": cb_plain,
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
        "email": escape(email_s),
        "email_line": escape(email_line),
        "signature": signature_html,
        "logo_header": logo_header,
        "callback_url": escape(cb_url),
        "callback_cta": cb_html,
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
    # Inject CTA after signature / before legal footer when placeholder absent.
    if cb_plain and "{callback_cta}" not in (plain_template or "") and "Заказать звонок" not in plain and cb_url not in plain:
        marker = "\n---\nВы получили это письмо"
        if marker in plain:
            plain = plain.replace(marker, cb_plain + marker, 1)
        elif "Отписаться" in plain:
            idx = plain.find("Отписаться")
            # insert before legal block start
            cut = plain.rfind("\n---\n", 0, idx)
            if cut >= 0:
                plain = plain[:cut] + cb_plain + plain[cut:]
            else:
                plain = plain.rstrip() + cb_plain
        else:
            plain = plain.rstrip() + cb_plain
    if cb_html and "{callback_cta}" not in (html_template or "") and href_marker_missing(html, cb_url):
        hr = '<hr style="border:none;border-top:1px solid #ddd;margin:1.5em 0 0.75em">'
        if hr in html:
            html = html.replace(hr, cb_html + "\n" + hr, 1)
        elif "Отписаться" in html:
            # Insert before legal footer paragraph block
            idx = html.find("Отписаться")
            cut = html.rfind("<hr", 0, idx)
            if cut < 0:
                cut = html.rfind("<div style=\"font-size:12px", 0, idx)
            if cut >= 0:
                html = html[:cut] + cb_html + "\n" + html[cut:]
            else:
                html = html.rstrip() + "\n" + cb_html
        else:
            html = html.rstrip() + "\n" + cb_html
    return plain, html


def href_marker_missing(html: str, url: str) -> bool:
    if not url:
        return True
    if url in html:
        return False
    if "name=\"fio\"" in html and "Заказать звонок" in html:
        return False
    return True
