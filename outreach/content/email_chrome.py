"""Canonical Quantum Labs outreach email visual system.

Source of truth: ``content/email/quantum-labs-outreach.html``
(design tokens and structure from the approved HTML mock).
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

# --- Design tokens (from quantum-labs-outreach.html) ---
PAGE_BG = "#f4f7fb"
CARD_BG = "#ffffff"
CARD_RADIUS = "16px"
CARD_SHADOW = "0 8px 28px rgba(20,43,79,.08)"
CARD_MAX = "640px"
INK = "#172033"
INK_BODY = "#25344d"
INK_HEAD = "#142a4a"
INK_MUTED = "#5a6780"
INK_SOFT = "#7a8599"
INK_LEGAL = "#8a94a6"
INK_LINK = "#2457e6"
INK_CONTACT = "#4f5c70"
INK_ICON = "#526a91"
BENEFITS_BG = "#f4f7fb"
LINE = "#e9edf4"
CONTACT_TOP = "#d7e0f0"
CTA_BG = "#ed5b3f"
FONT = "Arial,Helvetica,sans-serif"

CANONICAL_PATH = Path(__file__).resolve().parent / "email" / "quantum-labs-outreach.html"

_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")


def inline_md_to_html(text: str) -> str:
    """Escape HTML, then ``**bold**`` → ``<strong>`` (email-safe)."""
    parts: list[str] = []
    last = 0
    src = text or ""
    for m in _MD_BOLD.finditer(src):
        parts.append(escape(src[last : m.start()]))
        parts.append(
            f'<strong style="font-weight:700;color:{INK_HEAD};font-family:{FONT};">'
            + escape(m.group(1))
            + "</strong>"
        )
        last = m.end()
    parts.append(escape(src[last:]))
    return "".join(parts)

# Thin 20×20 stroke icons (canonical paths)
_SVG_MAIL = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    f'fill="none" stroke="{INK_ICON}" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" style="display:block;">'
    '<rect x="3" y="5" width="18" height="14" rx="2"></rect>'
    '<path d="m3 7 9 6 9-6"></path></svg>'
)
_SVG_WEB = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    f'fill="none" stroke="{INK_ICON}" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" style="display:block;">'
    '<circle cx="12" cy="12" r="9"></circle>'
    '<path d="M3 12h18"></path>'
    '<path d="M12 3c2.5 2.4 3.8 5.4 3.8 9S14.5 18.6 12 21c-2.5-2.4-3.8-5.4-3.8-9S9.5 5.4 12 3Z">'
    "</path></svg>"
)
_SVG_PHONE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" '
    f'fill="none" stroke="{INK_ICON}" stroke-width="1.8" stroke-linecap="round" '
    'stroke-linejoin="round" style="display:block;">'
    '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.3 19.3 0 0 1-6-6A19.8 19.8 0 0 1 '
    "2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .3 2 .7 2.9a2 2 0 0 1-.4 2.1L8.1 10a16 16 0 0 0 6 6"
    'l1.3-1.3a2 2 0 0 1 2.1-.4c.9.4 1.9.6 2.9.7A2 2 0 0 1 22 16.9Z"></path></svg>'
)


def logo_header_html(*, logo_url: str, company: str = "Quantum Labs") -> str:
    """Card header row: mark + wordmark."""
    url = (logo_url or "").strip()
    name = escape((company or "Quantum Labs").strip() or "Quantum Labs")
    mark = ""
    if url:
        mark = (
            f'<img src="{escape(url, quote=True)}" width="32" height="32" alt="{name}" '
            'style="display:block;border:0;">'
        )
    return (
        '<tr><td style="padding:28px 32px 22px;border-bottom:1px solid '
        f'{LINE};"><table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>'
        f'<td valign="middle" style="padding-right:10px;">{mark}</td>'
        f'<td valign="middle" style="font-size:18px;line-height:22px;font-weight:700;'
        f'letter-spacing:-.2px;color:{INK_HEAD};font-family:{FONT};">{name}</td>'
        "</tr></table></td></tr>"
    )


def soft_panel_html(inner_html: str) -> str:
    """Canonical mid-letter substrate — same #f4f7fb as the contact band."""
    body = (inner_html or "").strip()
    if not body:
        return ""
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'style="background:{BENEFITS_BG};border-radius:12px;margin:0 0 24px;">'
        f'<tr><td style="padding:20px 22px;">{body}</td></tr></table>'
    )


def benefits_box_html(*, title: str, items: list[str]) -> str:
    """Soft light-blue advantages block (canonical mid-letter panel)."""
    if not items:
        return ""
    title_s = escape(title or "Что получает ваша команда")
    rows = []
    for i, item in enumerate(items):
        margin = "0" if i == len(items) - 1 else "0 0 7px"
        rows.append(
            f'<p style="margin:{margin};font-size:15px;line-height:21px;color:#35445d;'
            f'font-family:{FONT};">• {inline_md_to_html(item)}</p>'
        )
    inner = (
        f'<p style="margin:0 0 11px;font-size:15px;line-height:20px;font-weight:700;'
        f'color:{INK_HEAD};font-family:{FONT};">{title_s}</p>'
        + "".join(rows)
    )
    return soft_panel_html(inner)


def cta_block_html(
    *,
    url: str,
    title: str,
    lead: str,
    button: str,
    reply_mailto: str | None = None,
) -> str:
    """Red-orange CTA button + short helper lines (canonical styling)."""
    href = escape(url, quote=True)
    title_s = escape(title)
    lead_s = escape(lead)
    button_s = escape(button)
    mail = (reply_mailto or "").strip() or "office@quantumlabs.ru"
    mailto = (
        f"mailto:{mail}"
        f"?subject=%D0%9F%D0%B5%D1%80%D0%B5%D0%B7%D0%B2%D0%BE%D0%BD%D0%B8%D1%82%D0%B5%20%D0%BC%D0%BD%D0%B5"
    )
    return (
        f'<p style="margin:24px 0 8px;font-size:17px;line-height:25px;font-weight:700;'
        f'color:{INK_HEAD};font-family:{FONT};">{title_s}</p>'
        f'<p style="margin:0 0 22px;font-size:15px;line-height:22px;color:{INK_MUTED};'
        f'font-family:{FONT};">{lead_s}</p>'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0"><tr>'
        f'<td bgcolor="{CTA_BG}" style="border-radius:9px;">'
        f'<a href="{href}" target="_blank" style="display:inline-block;padding:14px 22px;'
        f'font-size:15px;line-height:18px;font-weight:700;color:#ffffff;text-decoration:none;'
        f'border-radius:9px;font-family:{FONT};">{button_s}</a>'
        "</td></tr></table>"
        f'<p style="margin:12px 0 0;font-size:13px;line-height:19px;color:{INK_SOFT};'
        f'font-family:{FONT};">Откроется короткая форма: ФИО и телефон. '
        "Перезвоним в ближайшие минуты.</p>"
        f'<p style="margin:24px 0 0;font-size:16px;line-height:24px;color:{INK_BODY};'
        f'font-family:{FONT};">Если удобнее, просто '
        f'<a href="{escape(mailto, quote=True)}" style="color:{INK_LINK};text-decoration:underline;">'
        "ответьте на это письмо</a> с ФИО и телефоном.</p>"
    )


def _icon_img(src: str) -> str:
    """Hosted PNG — Gmail/Outlook strip inline SVG."""
    return (
        f'<img src="{escape(src, quote=True)}" width="20" height="20" alt="" '
        'style="display:block;border:0;outline:none;width:20px;height:20px;">'
    )


def contact_block_html(
    *,
    website: str,
    phone: str,
    email: str,
    closing: str = "Команда Quantum Labs",
    icon_base: str | None = None,
) -> str:
    """Light contact band with darker top edge + hosted PNG icons (email-safe)."""
    site = (website or "").strip()
    phone_s = (phone or "").strip()
    email_s = (email or "").strip()
    site_host = site
    if site_host.startswith("https://"):
        site_host = site_host[8:]
    elif site_host.startswith("http://"):
        site_host = site_host[7:]
    site_host = site_host.rstrip("/")
    site_href = site if "://" in site else (f"https://{site}" if site else "")
    base = (icon_base or "").rstrip("/") or "https://a.47z.ru/_ava_outreach"
    # /v2/ path busts Gmail image proxy cache of earlier PIL icons
    mail_icon = f"{base}/assets/brand/icons/v2/mail.png"
    web_icon = f"{base}/assets/brand/icons/v2/web.png"
    phone_icon = f"{base}/assets/brand/icons/v2/phone.png"

    rows: list[str] = []
    if email_s:
        rows.append(
            '<tr><td width="29" valign="middle" style="padding:0 9px 10px 0;">'
            f"{_icon_img(mail_icon)}</td>"
            f'<td style="padding:0 0 10px;font-size:14px;line-height:20px;font-family:{FONT};">'
            f'<a href="mailto:{escape(email_s, quote=True)}" style="color:{INK_CONTACT};'
            f'text-decoration:none;">{escape(email_s)}</a></td></tr>'
        )
    if site:
        rows.append(
            '<tr><td width="29" valign="middle" style="padding:0 9px 10px 0;">'
            f"{_icon_img(web_icon)}</td>"
            f'<td style="padding:0 0 10px;font-size:14px;line-height:20px;font-family:{FONT};">'
            f'<a href="{escape(site_href, quote=True)}" style="color:{INK_CONTACT};'
            f'text-decoration:none;">{escape(site_host or site)}</a></td></tr>'
        )
    if phone_s:
        tel = "tel:" + "".join(ch for ch in phone_s if ch.isdigit() or ch == "+")
        rows.append(
            '<tr><td width="29" valign="middle" style="padding:0 9px 0 0;">'
            f"{_icon_img(phone_icon)}</td>"
            f'<td style="font-size:14px;line-height:20px;font-family:{FONT};">'
            f'<a href="{escape(tel, quote=True)}" style="color:{INK_CONTACT};'
            f'text-decoration:none;">{escape(phone_s)}</a></td></tr>'
        )
    if not rows:
        return ""
    closing_s = escape(closing or "Команда Quantum Labs")
    return (
        f'<tr><td style="padding:23px 32px 24px;background:{BENEFITS_BG};'
        f'border-top:3px solid {CONTACT_TOP};">'
        f'<p style="margin:0 0 16px;font-size:15px;line-height:21px;font-weight:700;'
        f'color:{INK_HEAD};font-family:{FONT};">{closing_s}</p>'
        '<table role="presentation" cellspacing="0" cellpadding="0" border="0">'
        + "".join(rows)
        + "</table></td></tr>"
    )


LEGAL_FOOTER_HTML = f"""
<tr><td style="padding:20px 32px 28px;">
  <p style="margin:0 0 10px;font-size:11px;line-height:16px;color:{INK_LEGAL};font-family:{FONT};">Вы получили это письмо, потому что ваша компания указана в открытых источниках как организация, для которой могут быть актуальны сервисы платёжной инфраструктуры Quantum Labs, в том числе Quantum Payouts.</p>
  <p style="margin:0 0 10px;font-size:11px;line-height:16px;color:{INK_LEGAL};font-family:{FONT};">ООО «Квантум Лабс» · quantumlabs.ru · office@quantumlabs.ru</p>
  <p style="margin:0 0 10px;font-size:11px;line-height:16px;font-family:{FONT};"><a href="{{unsub_url}}" style="color:#6d7789;text-decoration:underline;">Отписаться от рассылки</a><span style="color:#a0a8b5;"> · </span><a href="mailto:{{unsub}}?subject=unsubscribe" style="color:#6d7789;text-decoration:underline;">написать для отписки</a></p>
  <p style="margin:0;font-size:11px;line-height:16px;color:{INK_LEGAL};font-family:{FONT};">Обработка обращений — в соответствии с применимым законодательством РФ, в том числе 152‑ФЗ. Письмо носит информационный характер и не является офертой.</p>
</td></tr>
"""


def wrap_letter_html(inner: str) -> str:
    """Full email document shell matching the canonical mock."""
    return (
        '<!doctype html>\n'
        '<html lang="ru"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="x-apple-disable-message-reformatting">'
        "<title>Quantum Labs</title></head>\n"
        f'<body style="margin:0;padding:0;background:{PAGE_BG};font-family:{FONT};'
        f'color:{INK};">\n'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'style="background:{PAGE_BG};"><tr>'
        f'<td align="center" style="padding:32px 16px;">\n'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" '
        f'style="max-width:{CARD_MAX};background:{CARD_BG};border-radius:{CARD_RADIUS};'
        f'overflow:hidden;box-shadow:{CARD_SHADOW};">\n'
        "{logo_header}\n"
        f'<tr><td style="padding:34px 32px 18px;"><div style="font-size:16px;line-height:24px;'
        f'color:{INK_BODY};font-family:{FONT};">\n'
        f"{inner}\n"
        "{callback_cta}\n"
        "</div></td></tr>\n"
        "{signature}\n"
        "{legal_html}\n"
        "</table></td></tr></table>\n"
        "</body></html>"
    )


def has_canonical_chrome(html: str) -> bool:
    raw = html or ""
    return PAGE_BG in raw and CARD_MAX in raw and "border-radius:16px" in raw
