"""LPR scoring, identity clusters, coverage matrix (rules-first)."""

from __future__ import annotations

import re
import uuid
from typing import Any


def _new_id() -> str:
    return str(uuid.uuid4())


def normalize_name_key(name: str | None) -> str:
    raw = re.sub(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", " ", (name or "").lower())
    return re.sub(r"\s+", " ", raw).strip()


def score_candidate(
    hit: dict[str, Any], *, roles: list[dict[str, Any]]
) -> dict[str, Any]:
    breakdown: dict[str, float] = {
        "has_name": 0.0,
        "role_match": 0.0,
        "has_email": 0.0,
        "has_profile": 0.0,
        "source_trust": 0.0,
    }
    name = (hit.get("full_name") or "").strip()
    if name:
        breakdown["has_name"] = 0.35
    role_guess = (hit.get("role_guess") or "").lower()
    best_role = ""
    for role in roles:
        labels = [str(x).lower() for x in (role.get("labels") or [])]
        if any(lbl and lbl in role_guess for lbl in labels):
            breakdown["role_match"] = 0.35 if role.get("primary") else 0.25
            best_role = str(role.get("id") or "")
            break
        # also match labels against name context title empty — skip
    if hit.get("email"):
        breakdown["has_email"] = 0.15
    if hit.get("profile_url"):
        breakdown["has_profile"] = 0.1
    trust = {
        "clients": 0.15,
        "dadata": 0.12,
        "telegram": 0.05,
        "web_import": 0.05,
        "vk": 0.03,
        "ok": 0.03,
        "tenchat": 0.03,
        "linkedin": 0.04,
    }
    breakdown["source_trust"] = float(trust.get(hit.get("source") or "", 0.02))
    total = round(sum(breakdown.values()), 4)
    out = dict(hit)
    out["id"] = hit.get("id") or _new_id()
    out["score"] = total
    out["score_breakdown"] = breakdown
    if best_role and not out.get("role_guess"):
        out["role_guess"] = best_role
    out.setdefault("status", "proposed")
    return out


def cluster_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group same-person signals by normalized name; never auto-merge (B2)."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    singles: list[dict[str, Any]] = []
    for c in candidates:
        key = normalize_name_key(c.get("full_name"))
        if not key:
            singles.append(c)
            continue
        by_key.setdefault(key, []).append(c)

    out: list[dict[str, Any]] = []
    for key, group in by_key.items():
        if len(group) == 1:
            out.append(group[0])
            continue
        cluster_id = _new_id()
        for c in group:
            item = dict(c)
            item["cluster_id"] = cluster_id
            item["status"] = "cluster_pending"
            item["evidence"] = {
                **(item.get("evidence") or {}),
                "cluster_reason": "same_normalized_name",
                "cluster_size": len(group),
                "approval_required": True,
            }
            out.append(item)
    out.extend(singles)
    return out


def build_coverage(
    candidates: list[dict[str, Any]], roles: list[dict[str, Any]]
) -> dict[str, Any]:
    """Committee coverage: roles × whether any non-rejected candidate matches."""
    active = [c for c in candidates if c.get("status") != "rejected"]
    rows = []
    missing = []
    for role in roles:
        rid = str(role.get("id") or "")
        labels = [str(x).lower() for x in (role.get("labels") or [])]
        matched = []
        for c in active:
            role_guess = (c.get("role_guess") or "").lower()
            if any(lbl and lbl in role_guess for lbl in labels):
                matched.append(c.get("id"))
        covered = bool(matched)
        rows.append(
            {
                "role_id": rid,
                "primary": bool(role.get("primary")),
                "covered": covered,
                "candidate_ids": matched,
                "sources": sorted(
                    {
                        c.get("source")
                        for c in active
                        if c.get("id") in matched and c.get("source")
                    }
                ),
            }
        )
        if not covered:
            missing.append(rid)
    return {"roles": rows, "missing_roles": missing}


def reject_candidate(store: Any, candidate_id: str) -> dict[str, Any] | None:
    return store.set_candidate_status(candidate_id, "rejected")
