#!/usr/bin/env python3
"""Partner-channel sender — ONLY from rdv@quantumlabs.ru.

Safety:
  - Default: dry-run (no SMTP).
  - PARTNER_SEND_ENABLED must be true to send.
  - MAIL_USERNAME must be rdv@quantumlabs.ru (office@ is refused).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import smtplib
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, make_msgid
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

ROOT = Path(__file__).resolve().parents[1]
CRM_JSON = ROOT / "crm" / "partners.json"
CRM_CSV = ROOT / "crm" / "partners.csv"
LOG_DIR = ROOT / "logs"
ALLOWED_FROM = "rdv@quantumlabs.ru"
BLOCKED_FROM = {"office@quantumlabs.ru"}


def _business_days_ahead(start: date, n: int) -> date:
    d = start
    left = n
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def load_campaign() -> dict:
    return json.loads(CRM_JSON.read_text(encoding="utf-8"))


def save_campaign(data: dict) -> None:
    CRM_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = [
        "company",
        "website",
        "contact",
        "email",
        "phone",
        "telegram",
        "model",
        "fintech_experience",
        "priority",
        "fit_reason",
        "contact_source",
        "channel",
        "sent_at",
        "from_address",
        "reply",
        "next_contact",
        "followup1_date",
        "followup2_date",
        "status",
        "comment",
    ]
    with CRM_CSV.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for p in data["partners"]:
            w.writerow(p)


def parse_email_file(path: Path) -> tuple[str, str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    to = subject = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.lower().startswith("to:"):
            to = line.split(":", 1)[1].strip()
        elif line.lower().startswith("subject:"):
            subject = line.split(":", 1)[1].strip()
        elif line.strip() == "":
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip() + "\n"
    return to, subject, body


def load_html_for(plain_path: Path) -> str | None:
    """Prefer companion .html with clickable Quantum Payouts → quantumpayouts.ru."""
    html_path = plain_path.with_suffix(".html")
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return None


def plain_to_fallback_html(plain: str) -> str:
    from html import escape

    site = "https://quantumpayouts.ru"
    link = f'<a href="{site}" style="color:#0b57d0;text-decoration:underline;">'
    escaped_lines = []
    for line in plain.splitlines():
        if not line.strip():
            escaped_lines.append("<br>")
            continue
        e = escape(line)
        e = e.replace("Quantum Payouts", f"{link}Quantum Payouts</a>")
        e = e.replace(escape(site), f'{link}{escape(site.replace("https://", ""))}</a>')
        e = e.replace("quantumpayouts.ru", f"{link}quantumpayouts.ru</a>")
        escaped_lines.append(f"<p>{e}</p>")
    return (
        '<!DOCTYPE html><html lang="ru"><body style="font-family:Georgia,serif;'
        'line-height:1.55;color:#1a1a1a;max-width:640px;">'
        + "".join(escaped_lines)
        + "</body></html>"
    )


def assert_from_ok(username: str) -> None:
    u = (username or "").strip().lower()
    if u in BLOCKED_FROM:
        raise SystemExit(
            f"Refusing send: MAIL_USERNAME={username!r}. "
            f"Partner channel must use {ALLOWED_FROM} only."
        )
    if u != ALLOWED_FROM:
        raise SystemExit(
            f"Refusing send: MAIL_USERNAME must be {ALLOWED_FROM}, got {username!r}."
        )


def send_one(*, to: str, subject: str, plain: str, html: str | None = None) -> str:
    host = os.environ["MAIL_SMTP_HOST"].strip()
    port = int(os.getenv("MAIL_SMTP_PORT", "465"))
    user = os.environ["MAIL_USERNAME"].strip()
    password = os.environ["MAIL_PASSWORD"]
    from_name = os.getenv("MAIL_FROM_NAME", "Денис Рябов · Quantum Payouts").strip()
    reply = os.getenv("MAIL_REPLY_TO", user).strip() or user
    assert_from_ok(user)

    mid = make_msgid(domain=user.split("@")[-1])
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply
    msg["Message-ID"] = mid
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
    msg["X-Campaign"] = "quantum-payouts-partner-channel"
    html_body = html or plain_to_fallback_html(plain)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(host, port, timeout=float(os.getenv("MAIL_SMTP_TIMEOUT_SECONDS", "20"))) as s:
        s.login(user, password)
        s.send_message(msg)
    return mid.strip().strip("<>")


def main() -> int:
    ap = argparse.ArgumentParser(description="Send Quantum Payouts partner-channel emails via rdv@")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only (default if SEND not enabled)")
    ap.add_argument("--priority", default="A", help="A, B, C, or ALL")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--ids", default="", help="Comma-separated partner ids")
    ap.add_argument("--delay", type=int, default=90, help="Seconds between sends")
    args = ap.parse_args()

    enabled = os.getenv("PARTNER_SEND_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    dry = args.dry_run or not enabled
    if not enabled and not args.dry_run:
        print(
            "PARTNER_SEND_ENABLED is false — forcing dry-run. "
            f"Configure SMTP for {ALLOWED_FROM}, then set PARTNER_SEND_ENABLED=true."
        )
    if not dry:
        assert_from_ok(os.environ.get("MAIL_USERNAME", ""))
        for key in ("MAIL_SMTP_HOST", "MAIL_PASSWORD"):
            if not os.environ.get(key):
                raise SystemExit(f"Missing required env: {key}")

    data = load_campaign()
    ids = {x.strip() for x in args.ids.split(",") if x.strip()}
    selected = []
    for p in data["partners"]:
        if not p.get("email"):
            continue
        if p.get("sent_at"):
            continue
        if ids and p["id"] not in ids:
            continue
        if args.priority.upper() != "ALL" and p.get("priority") != args.priority.upper():
            continue
        selected.append(p)
        if len(selected) >= args.limit:
            break

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"send_{_utc_now().strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    print(f"selected={len(selected)} dry_run={dry} from={ALLOWED_FROM} log={log_path}")

    today = date.today()
    for i, p in enumerate(selected):
        email_path = ROOT / p["email_file"]
        to, subject, body = parse_email_file(email_path)
        html = load_html_for(email_path)
        assert to.lower() == p["email"].lower()
        entry = {
            "ts": _utc_now().isoformat().replace("+00:00", "Z"),
            "id": p["id"],
            "to": to,
            "subject": subject,
            "dry_run": dry,
            "from": ALLOWED_FROM,
            "has_html": bool(html),
        }
        if dry:
            print(f"[dry-run] would send → {to} ({p['company']}) html={bool(html)}")
            p["status"] = "предложение подготовлено"
            p["comment"] = (
                f"Dry-run OK. Waiting for {ALLOWED_FROM} mailbox. Do not send from office@."
            )
        else:
            mid = send_one(to=to, subject=subject, plain=body, html=html)
            now = _utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
            p["sent_at"] = now
            p["from_address"] = ALLOWED_FROM
            p["status"] = "отправлено"
            p["followup1_date"] = _business_days_ahead(today, 3).isoformat()
            p["followup2_date"] = _business_days_ahead(today, 7).isoformat()
            p["next_contact"] = p["followup1_date"]
            p["comment"] = f"Sent Message-ID={mid}"
            entry["message_id"] = mid
            print(f"[sent] {to} mid={mid}")
            if i < len(selected) - 1 and args.delay > 0:
                time.sleep(args.delay)
        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    save_campaign(data)
    print("CRM updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
