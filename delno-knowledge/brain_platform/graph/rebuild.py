"""G2 — populate graph from contacts, companies, threads (idempotent)."""

from __future__ import annotations

import json
from typing import Any

from brain_platform.graph.store import GraphStore


def _loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def rebuild_graph_from_corpus(repo, *, tenant_id: str) -> dict[str, Any]:
    """
    Build person/company/thread_topic entities and works_at / participant_of edges
    from existing contacts + threads. Idempotent via stable slug ids.
    """
    graph = GraphStore(repo.conn)
    stats = {
        "persons": 0,
        "companies": 0,
        "threads": 0,
        "edges_works_at": 0,
        "edges_participant": 0,
        "product": 0,
    }

    # Product stub
    product_id = graph.upsert_entity(
        tenant_id=tenant_id,
        kind="product",
        canonical_name="Quantum Payouts",
        metadata={"source": "bootstrap"},
        visibility="company",
        aliases=["Quantum Labs", "квантум", "payouts"],
    )
    stats["product"] = 1

    company_ids: dict[str, str] = {}
    contacts = repo.conn.execute(
        "SELECT * FROM contacts WHERE tenant_id = ? AND status = 'active'",
        (tenant_id,),
    ).fetchall()

    for c in contacts:
        name = (c["display_name"] or "").strip() or "Unknown"
        person_id = graph.upsert_entity(
            tenant_id=tenant_id,
            kind="person",
            canonical_name=name,
            entity_id=f"ent-person-{c['id']}",
            metadata={
                "contact_id": c["id"],
                "emails": _loads(c["emails_json"], []),
                "phones": _loads(c["phones_json"], []),
                "title": c["title"],
                "source": c["source"],
            },
            visibility=c["visibility"] or "company",
            aliases=_loads(c["emails_json"], []),
        )
        stats["persons"] += 1

        company = (c["company_name"] or "").strip()
        if company:
            key = company.lower()
            if key not in company_ids:
                company_ids[key] = graph.upsert_entity(
                    tenant_id=tenant_id,
                    kind="company",
                    canonical_name=company,
                    metadata={"source": "contacts"},
                    visibility="company",
                )
                stats["companies"] += 1
            graph.upsert_edge(
                tenant_id=tenant_id,
                source_entity_id=person_id,
                target_entity_id=company_ids[key],
                relation_type="works_at",
                confidence=0.95,
                visibility="company",
            )
            stats["edges_works_at"] += 1

            # company related to product (soft)
            graph.upsert_edge(
                tenant_id=tenant_id,
                source_entity_id=company_ids[key],
                target_entity_id=product_id,
                relation_type="related_to",
                confidence=0.4,
                review_status="pending",
                visibility="company",
            )

    threads = repo.conn.execute(
        "SELECT * FROM threads WHERE tenant_id = ?",
        (tenant_id,),
    ).fetchall()
    for t in threads:
        subject = (t["subject"] or "").strip() or "(no subject)"
        tid = graph.upsert_entity(
            tenant_id=tenant_id,
            kind="thread_topic",
            canonical_name=subject[:200],
            entity_id=f"ent-thread-{t['id']}",
            metadata={
                "thread_id": t["id"],
                "channel": t["channel"],
                "topics": _loads(t["topics_json"], []),
                "last_message_at": t["last_message_at"],
            },
            visibility=t["visibility"] or "restricted",
        )
        stats["threads"] += 1

        # Link participants if we can map contact ids
        for pid in _loads(t["participant_ids_json"], []):
            # participant_ids may be contact ids or emails
            person_eid = None
            row = repo.conn.execute(
                "SELECT id FROM contacts WHERE tenant_id = ? AND id = ?",
                (tenant_id, pid),
            ).fetchone()
            if row:
                person_eid = f"ent-person-{row['id']}"
            else:
                crow = repo.conn.execute(
                    """
                    SELECT contact_id FROM contact_emails
                    WHERE tenant_id = ? AND email = ?
                    """,
                    (tenant_id, str(pid).lower()),
                ).fetchone()
                if crow:
                    person_eid = f"ent-person-{crow['contact_id']}"
            if not person_eid:
                continue
            exists = repo.conn.execute(
                "SELECT 1 FROM entities WHERE id = ?", (person_eid,)
            ).fetchone()
            if not exists:
                continue
            graph.upsert_edge(
                tenant_id=tenant_id,
                source_entity_id=person_eid,
                target_entity_id=tid,
                relation_type="participant_of",
                confidence=0.9,
                visibility="restricted",
            )
            stats["edges_participant"] += 1

    # document entities for FAQ docs (owns_doc light)
    faq_docs = repo.conn.execute(
        """
        SELECT id, title FROM documents
        WHERE tenant_id = ? AND type = 'faq' AND status = 'active'
        LIMIT 200
        """,
        (tenant_id,),
    ).fetchall()
    for d in faq_docs:
        doc_ent = graph.upsert_entity(
            tenant_id=tenant_id,
            kind="document",
            canonical_name=(d["title"] or d["id"])[:200],
            entity_id=f"ent-doc-{d['id']}",
            metadata={"document_id": d["id"]},
            visibility="company",
        )
        graph.upsert_edge(
            tenant_id=tenant_id,
            source_entity_id=product_id,
            target_entity_id=doc_ent,
            relation_type="owns_doc",
            source_document_id=d["id"],
            confidence=0.8,
            visibility="company",
        )

    stats["entities_total"] = repo.conn.execute(
        "SELECT count(*) AS n FROM entities WHERE tenant_id = ?", (tenant_id,)
    ).fetchone()["n"]
    stats["edges_total"] = repo.conn.execute(
        "SELECT count(*) AS n FROM edges WHERE tenant_id = ?", (tenant_id,)
    ).fetchone()["n"]
    stats["ok"] = True
    return stats
