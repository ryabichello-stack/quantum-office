#!/usr/bin/env python3
"""Partner-channel sender — ONLY from rdv@quantumlabs.ru.

ISOLATION FROM AVA-OUTREACH (office@):
  - Does NOT use /opt/ava-outreach, outbox.db, Bitrix outreach queue,
    OUTREACH_ENABLED, or OUTREACH_DAILY_LIMIT.
  - Sends via its own SMTP login (rdv@) and partner-channel CRM only.
  - office@quantumlabs.ru is hard-refused so pawnshop/outreach caps are untouched.

Safety:
  - Default: dry-run (no SMTP).
  - PARTNER_SEND_ENABLED must be true to send.
  - MAIL_USERNAME must be rdv@quantumlabs.ru.
"""

from __future__ import annotations

import argparse
import csv
import imaplib
import json
import os
import random
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
# Never load outreach/mailer env from prod paths — partner channel is a separate mailbox/budget.
FORBIDDEN_ENV_PATHS = (
    Path("/opt/ava-outreach/.env"),
    Path("/opt/ava-mailer/.env"),
)
ENV_CANDIDATES = (
    ROOT / "smtp.local.env",  # visible in IDE (preferred)
    ROOT / ".env",
)


def load_local_env() -> Path | None:
    """Load KEY=VALUE from smtp.local.env / .env into os.environ (do not override existing)."""
    for path in ENV_CANDIDATES:
        if not path.is_file():
            continue
        resolved = path.resolve()
        for bad in FORBIDDEN_ENV_PATHS:
            try:
                if resolved == bad.resolve():
                    raise SystemExit(f"Refusing to load outreach/mailer env: {bad}")
            except FileNotFoundError:
                pass
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val
        return path
    return None


def smtp_creds() -> tuple[str, int, str, str, str, str]:
    """Resolve SMTP settings; prefer PARTNER_MAIL_* so outreach MAIL_* never leaks in."""
    host = (
        os.getenv("PARTNER_MAIL_SMTP_HOST")
        or os.getenv("MAIL_SMTP_HOST")
        or ""
    ).strip()
    port = int(
        os.getenv("PARTNER_MAIL_SMTP_PORT")
        or os.getenv("MAIL_SMTP_PORT")
        or "465"
    )
    user = (
        os.getenv("PARTNER_MAIL_USERNAME")
        or os.getenv("MAIL_USERNAME")
        or ""
    ).strip()
    password = os.getenv("PARTNER_MAIL_PASSWORD") or os.getenv("MAIL_PASSWORD") or ""
    from_name = (
        os.getenv("PARTNER_MAIL_FROM_NAME")
        or os.getenv("MAIL_FROM_NAME")
        or "Денис Рябов · Quantum Payouts"
    ).strip()
    reply = (
        os.getenv("PARTNER_MAIL_REPLY_TO")
        or os.getenv("MAIL_REPLY_TO")
        or user
    ).strip() or user
    return host, port, user, password, from_name, reply


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
    host, port, user, password, from_name, reply = smtp_creds()
    assert_from_ok(user)
    if not host or not password:
        raise SystemExit("Missing SMTP host/password for rdv@ (partner channel only).")

    mid = make_msgid(domain=user.split("@")[-1])
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((from_name, user))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Reply-To"] = reply
    msg["Message-ID"] = mid
    msg["List-Unsubscribe"] = f"<mailto:{user}?subject=unsubscribe>"
    msg["X-Campaign"] = "quantum-payouts-partner-channel"
    msg["X-Partner-Channel"] = "isolated-from-ava-outreach"
    html_body = html or plain_to_fallback_html(plain)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    timeout = float(
        os.getenv("PARTNER_MAIL_SMTP_TIMEOUT_SECONDS")
        or os.getenv("MAIL_SMTP_TIMEOUT_SECONDS")
        or "20"
    )
    with smtplib.SMTP_SSL(host, port, timeout=timeout) as s:
        s.login(user, password)
        s.send_message(msg)

    # Keep a copy in the mailbox Sent folder (Mail.ru does not always auto-save SMTP).
    try:
        save_to_sent(msg)
    except Exception as exc:  # noqa: BLE001
        print(f"WARNING: SMTP ok but Sent copy failed for {to}: {exc}")

    return mid.strip().strip("<>")


def save_to_sent(msg: MIMEMultipart) -> str:
    """APPEND the exact outbound message into IMAP Sent for rdv@."""
    user = (os.getenv("PARTNER_MAIL_USERNAME") or os.getenv("MAIL_USERNAME") or "").strip()
    password = os.getenv("PARTNER_MAIL_PASSWORD") or os.getenv("MAIL_PASSWORD") or ""
    assert_from_ok(user)
    host = (os.getenv("IMAP_HOST") or os.getenv("MAIL_IMAP_HOST") or "imap.mail.ru").strip()
    port = int(os.getenv("IMAP_PORT") or os.getenv("MAIL_IMAP_PORT") or "993")
    preferred = (
        os.getenv("IMAP_SENT_FOLDER")
        or os.getenv("MAIL_IMAP_SENT_FOLDER")
        or ""
    ).strip()

    raw = msg.as_bytes()
    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        typ, data = imap.list()
        folders: list[str] = []
        if typ == "OK" and data:
            for item in data:
                if not item:
                    continue
                line = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item)
                # LIST (... ) "." "Folder"
                if '"' in line:
                    folders.append(line.split('"')[-2])
        candidates = []
        if preferred:
            candidates.append(preferred)
        for name in (
            "Отправленные",
            "Sent",
            "Sent Items",
            "Sent Messages",
            "INBOX.Sent",
            "INBOX.Отправленные",
        ):
            if name not in candidates:
                candidates.append(name)
        for f in folders:
            low = f.lower()
            if "sent" in low or "отправ" in low:
                if f not in candidates:
                    candidates.append(f)

        last_err = None
        for folder in candidates:
            try:
                typ, _ = imap.append(folder, "\\Seen", imaplib.Time2Internaldate(time.time()), raw)
                if typ == "OK":
                    return folder
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                continue
        raise RuntimeError(f"Could not APPEND to Sent; tried {candidates!r}; last={last_err}")
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="Send Quantum Payouts partner-channel emails via rdv@")
    ap.add_argument("--dry-run", action="store_true", help="Print actions only (default if SEND not enabled)")
    ap.add_argument("--priority", default="A", help="A, B, C, or ALL")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--ids", default="", help="Comma-separated partner ids")
    ap.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Fixed seconds between sends (0 = random 10–15 min jitter)",
    )
    ap.add_argument("--delay-min", type=int, default=600, help="Min jitter seconds (default 10 min)")
    ap.add_argument("--delay-max", type=int, default=900, help="Max jitter seconds (default 15 min)")
    args = ap.parse_args()

    env_path = load_local_env()
    if env_path:
        print(f"loaded env from {env_path}")
    else:
        print("no local env file found (smtp.local.env / .env); using process env only")

    enabled = os.getenv("PARTNER_SEND_ENABLED", "false").lower() in ("1", "true", "yes", "on")
    dry = args.dry_run or not enabled
    if not enabled and not args.dry_run:
        print(
            "PARTNER_SEND_ENABLED is false — forcing dry-run. "
            f"Configure SMTP for {ALLOWED_FROM}, then set PARTNER_SEND_ENABLED=true."
        )
    if not dry:
        host, _, user, password, _, _ = smtp_creds()
        assert_from_ok(user)
        if not host or not password:
            raise SystemExit(
                "Missing PARTNER/MAIL SMTP host or password for rdv@. "
                "Fill partner-channel/smtp.local.env — do not use ava-outreach/.env."
            )
        print(f"SMTP account: {user} (isolated from office@ outreach limits)")
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
            "isolated_from_outreach": True,
        }
        if dry:
            print(f"[dry-run] would send → {to} ({p['company']}) html={bool(html)}")
            p["status"] = "предложение подготовлено"
            p["comment"] = (
                f"Dry-run OK. Separate rdv@ channel — does not use office@ outreach limits."
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
            p["comment"] = f"Sent via rdv@ (isolated). Message-ID={mid}"
            entry["message_id"] = mid
            print(f"[sent] {to} mid={mid}")
            if i < len(selected) - 1:
                if args.delay > 0:
                    wait_s = args.delay
                else:
                    lo = max(0, min(args.delay_min, args.delay_max))
                    hi = max(lo, max(args.delay_min, args.delay_max))
                    wait_s = random.randint(lo, hi) if hi > 0 else 0
                if wait_s > 0:
                    print(f"waiting {wait_s}s (~{wait_s/60:.1f} min) before next send")
                    time.sleep(wait_s)
        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(json.dumps(entry, ensure_ascii=False) + "\n")

    save_campaign(data)
    print("CRM updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
