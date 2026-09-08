"""One-shot: promote mail_attachment questionnaire text into office-assistant docs."""

from __future__ import annotations

import logging
from typing import Any

from brain_platform.db.factory import get_brain_repo
from brain_platform.ingest.extract_text import looks_like_connection_data

logger = logging.getLogger("brain.ingest.reclassify_attachments")


def reclassify_mail_attachments(*, tenant_id: str = "quantum-labs") -> dict[str, Any]:
    repo = get_brain_repo()
    rows = repo.conn.execute(
        """
        SELECT id, path, filename, text_excerpt, visibility, content_hash, source
        FROM files
        WHERE tenant_id=? AND source='mail_attachment' AND status='active'
        """,
        (tenant_id,),
    ).fetchall()
    promoted = 0
    skipped = 0
    for r in rows:
        text = (r["text_excerpt"] or "").strip()
        if not text or not looks_like_connection_data(text):
            skipped += 1
            continue
        title = f"Данные для подключения (вложение): {r['filename']}"
        repo.promote_connection_settings_doc(
            tenant_id=tenant_id,
            title=title,
            body=f"## Вложение: {r['filename']}\n\n{text[:15000]}",
            source=f"mail-attachment-file:{r['id']}",
            subject_hint=r["filename"],
        )
        # Flip file visibility so future searches via file docs also work.
        if r["visibility"] != "company":
            repo.conn.execute(
                "UPDATE files SET visibility='company' WHERE id=?",
                (r["id"],),
            )
            repo.conn.commit()
            repo.upsert_document(
                doc_id=f"doc-{r['id']}",
                tenant_id=tenant_id,
                title=f"File: {r['filename']}",
                doc_type="file",
                body=(
                    f"# File: {r['filename']}\n\nPath: `{r['path']}`\n"
                    f"Source: mail_attachment\n\n{text[:15000]}"
                ),
                visibility="company",
                acl={
                    "allow_users": [],
                    "allow_groups": ["group:management", "group:sales", "group:ops"],
                    "allow_services": [
                        "service:cursor-admin",
                        "service:text-secretary",
                        "service:voice-office",
                    ],
                    "deny_users": [],
                    "deny_groups": [],
                },
                channels=["office-assistant"],
                source="file:mail_attachment",
                index_zone="private",
            )
        promoted += 1
        logger.info("promoted attachment %s", r["filename"])
    return {
        "ok": True,
        "scanned": len(rows),
        "promoted": promoted,
        "skipped": skipped,
    }


if __name__ == "__main__":
    import json
    import os

    from dotenv import load_dotenv

    load_dotenv()
    tenant = os.getenv("BRAIN_TENANT_ID", "quantum-labs")
    print(json.dumps(reclassify_mail_attachments(tenant_id=tenant), ensure_ascii=False, indent=2))
