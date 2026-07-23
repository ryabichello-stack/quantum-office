"""CLI: python -m brain_platform …"""

from __future__ import annotations

import argparse
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from brain_platform.db.connection import init_db
from brain_platform.db.factory import get_brain_repo
from brain_platform.db.repository import BrainRepository
from brain_platform.ingest.files import ingest_files
from brain_platform.ingest.legacy_faq import ingest_legacy_faq
from brain_platform.ingest.mail import ingest_mailbox
from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brain", description="Quantum Labs Second Brain CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-db", help="Create/migrate brain SQLite schema")
    p_init.add_argument("--db", default=None)

    p_init_pg = sub.add_parser("init-pg", help="Apply Postgres+pgvector schema")
    p_migrate = sub.add_parser("sync-pg", help="Copy SQLite corpus → Postgres (full refresh)")
    p_migrate.add_argument("--sqlite", default=None)
    p_migrate.add_argument("--no-truncate", action="store_true")

    p_ingest = sub.add_parser("ingest", help="Run ingest (faq/files/mail)")
    p_ingest.add_argument("--sources", default="faq,files,mail")
    p_ingest.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))
    p_ingest.add_argument("--mail-limit", type=int, default=100)
    p_ingest.add_argument("--file-limit", type=int, default=500)

    p_search = sub.add_parser("search", help="ACL search")
    p_search.add_argument("query")
    p_search.add_argument("--principal", default="service:cursor-admin")
    p_search.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))
    p_search.add_argument("--admin", action="store_true")
    p_search.add_argument("--groups", default="")
    p_search.add_argument(
        "--mode",
        default=os.getenv("BRAIN_SEARCH_MODE", "hybrid"),
        choices=["keyword", "semantic", "hybrid"],
    )

    p_contacts = sub.add_parser("contacts", help="Find contacts")
    p_contacts.add_argument("--q", default="")
    p_contacts.add_argument("--principal", default="service:text-secretary")
    p_contacts.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))

    p_embed = sub.add_parser("embed-backfill", help="Embed chunks missing vectors")
    p_embed.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))
    p_embed.add_argument("--limit", type=int, default=500)
    p_embed.add_argument("--all", action="store_true", help="Re-embed even if present")

    p_repair = sub.add_parser("repair-contacts", help="Rebuild contact names from mail bodies")
    p_repair.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))
    p_repair.add_argument("--limit", type=int, default=3000)

    p_stats = sub.add_parser("stats")
    p_stats.add_argument("--tenant", default=os.getenv("BRAIN_TENANT_ID", "quantum-labs"))

    args = parser.parse_args(argv)
    conn = init_db()
    repo = BrainRepository(conn)

    if args.cmd == "init-db":
        print(json.dumps({"ok": True, "stats": repo.stats(os.getenv("BRAIN_TENANT_ID", "quantum-labs"))}))
        return 0

    if args.cmd == "init-pg":
        from brain_platform.db.pg import init_postgres

        pg = init_postgres()
        pg.close()
        print(json.dumps({"ok": True, "backend": "postgres", "schema": "applied"}))
        return 0

    if args.cmd == "sync-pg":
        from brain_platform.db.connection import default_db_path
        from brain_platform.db.migrate_sqlite_to_pg import migrate
        from brain_platform.db.pg import database_url

        sqlite_path = args.sqlite or str(default_db_path())
        dsn = database_url()
        if not dsn:
            print(json.dumps({"ok": False, "error": "BRAIN_DATABASE_URL missing"}))
            return 2
        out = migrate(sqlite_path, dsn, truncate=not args.no_truncate)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0 if out.get("ok") else 1

    if args.cmd == "ingest":
        sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        out = {}
        if "faq" in sources:
            out["faq"] = ingest_legacy_faq(repo, tenant_id=args.tenant)
        if "files" in sources:
            out["files"] = ingest_files(repo, tenant_id=args.tenant, limit=args.file_limit)
        if "mail" in sources:
            out["mail"] = ingest_mailbox(
                repo, tenant_id=args.tenant, direction="both", limit=args.mail_limit
            )
        # Keep Postgres search index fresh when configured
        if (os.getenv("BRAIN_DATABASE_URL") or "").strip():
            try:
                from brain_platform.db.connection import default_db_path
                from brain_platform.db.migrate_sqlite_to_pg import migrate
                from brain_platform.db.pg import database_url

                out["sync_pg"] = migrate(str(default_db_path()), database_url(), truncate=True)
            except Exception as exc:  # noqa: BLE001
                out["sync_pg"] = {"ok": False, "error": str(exc)}
        out["stats"] = repo.stats(args.tenant)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "search":
        groups = tuple(g.strip() for g in args.groups.split(",") if g.strip())
        principal = Principal(
            principal_id=args.principal,
            tenant_id=args.tenant,
            groups=groups,
            is_admin=args.admin or args.principal == "service:cursor-admin",
            user_id="cli" if args.admin or args.principal == "service:cursor-admin" else None,
        )
        search_repo = get_brain_repo()
        result = BrainSearch(search_repo).retrieve(principal, args.query, mode=args.mode)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.cmd == "embed-backfill":
        out = repo.backfill_embeddings(
            tenant_id=args.tenant,
            limit=args.limit,
            only_missing=not args.all,
        )
        out["stats"] = repo.stats(args.tenant)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "contacts":
        principal = Principal(
            principal_id=args.principal,
            tenant_id=args.tenant,
            is_admin=False,
        )
        contacts = repo.find_contacts(principal, q=args.q)
        print(json.dumps({"count": len(contacts), "contacts": contacts}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "repair-contacts":
        from brain_platform.ingest.repair_contacts import repair_contacts_from_mail

        out = repair_contacts_from_mail(repo, tenant_id=args.tenant, limit=args.limit)
        out["stats"] = repo.stats(args.tenant)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "stats":
        print(json.dumps(repo.stats(args.tenant), indent=2))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
