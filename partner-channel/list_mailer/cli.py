#!/usr/bin/env python3
"""CLI for partner list-mailer — schedule/send from files without ava-outreach limits.

Examples (on prod /opt/partner-channel):
  python3 -m list_mailer.cli import-partners
  python3 -m list_mailer.cli status
  python3 -m list_mailer.cli send --limit 50 --delay-min 600 --delay-max 900
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from list_mailer import smtp_send  # noqa: E402
from list_mailer.store import ALLOWED_FROM, Store  # noqa: E402


def cmd_import_partners(_: argparse.Namespace) -> int:
    crm = json.loads((ROOT / "crm" / "partners.json").read_text(encoding="utf-8"))
    store = Store()
    cid = store.upsert_campaign(
        slug="quantum-payouts-partner-channel",
        title="Quantum Payouts partner channel",
        from_email=ALLOWED_FROM,
        notes="Isolated from office@ OUTREACH_DAILY_LIMIT",
    )
    n = 0
    for p in crm["partners"]:
        email = (p.get("email") or "").strip()
        if not email:
            continue
        plain = str(ROOT / p["email_file"])
        html = str(Path(plain).with_suffix(".html"))
        store.add_recipient(
            campaign_id=cid,
            email=email,
            company=p.get("company") or "",
            priority=p.get("priority") or "",
            subject=p.get("subject") or "",
            plain_path=plain,
            html_path=html if Path(html).exists() else "",
        )
        n += 1
    print(f"imported {n} recipients into campaign_id={cid}")
    return 0


def cmd_status(_: argparse.Namespace) -> int:
    store = Store()
    for row in store.list_campaigns():
        print({**dict(row), "stats": store.stats(row["id"])})
    print({"sent_today": store.sent_today(), "from": ALLOWED_FROM})
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    env_path = smtp_send.load_env()
    print(f"env={env_path}")
    os.environ["PARTNER_SEND_ENABLED"] = "true"
    store = Store()
    campaigns = store.list_campaigns()
    if not campaigns:
        raise SystemExit("No campaigns — run import-partners first")
    cid = int(campaigns[0]["id"])
    pending = store.pending(campaign_id=cid, limit=args.limit)
    print(f"pending={len(pending)} delay={args.delay_min}-{args.delay_max}s")
    for i, r in enumerate(pending):
        plain = Path(r.plain_path).read_text(encoding="utf-8")
        low = plain[:40].lower()
        if low.startswith("to:") or low.startswith("subject:") or "\nsubject:" in plain[:200].lower():
            lines = plain.splitlines()
            body_start = 0
            for j, line in enumerate(lines):
                if line.strip() == "":
                    body_start = j + 1
                    break
            plain = "\n".join(lines[body_start:]).strip() + "\n"
        html = None
        if r.html_path and Path(r.html_path).exists():
            html = Path(r.html_path).read_text(encoding="utf-8")
        try:
            mid = smtp_send.send_email(to=r.email, subject=r.subject, plain=plain, html=html)
            store.mark_sent(r.id, message_id=mid)
            store.bump_sent_today()
            print(f"[sent] {r.email} mid={mid}")
        except Exception as exc:  # noqa: BLE001
            store.mark_failed(r.id, str(exc))
            print(f"[error] {r.email}: {exc}")
            continue
        if i < len(pending) - 1:
            wait_s = random.randint(args.delay_min, args.delay_max)
            print(f"waiting {wait_s}s")
            time.sleep(wait_s)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Partner list-mailer CLI (rdv@)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("import-partners")
    sub.add_parser("status")
    p_send = sub.add_parser("send")
    p_send.add_argument("--limit", type=int, default=50)
    p_send.add_argument("--delay-min", type=int, default=600)
    p_send.add_argument("--delay-max", type=int, default=900)
    args = ap.parse_args()
    if args.cmd == "import-partners":
        return cmd_import_partners(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "send":
        return cmd_send(args)
    raise SystemExit(f"unknown cmd {args.cmd}")


if __name__ == "__main__":
    raise SystemExit(main())
