"""S3 eval harness — recall/citation/ACL smoke over fixed cases."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from brain_platform.search.engine import BrainSearch
from brain_platform.security.acl import Principal

DEFAULT_CASES = Path(__file__).with_name("cases.yaml")


def load_cases(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_CASES
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    cases = data.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError("cases.yaml must contain a list under 'cases'")
    return cases


def _principal_from_case(case: dict[str, Any]) -> Principal:
    pid = case.get("principal") or "service:cursor-admin"
    is_admin = pid == "service:cursor-admin"
    return Principal(
        principal_id=pid,
        tenant_id=case.get("tenant_id") or "quantum-labs",
        groups=tuple(case.get("groups") or ()),
        is_admin=is_admin,
        user_id="eval" if is_admin else None,
    )


def _contains_any(text: str, needles: list[str]) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles if n)


def run_case(search: BrainSearch, case: dict[str, Any]) -> dict[str, Any]:
    principal = _principal_from_case(case)
    mode = case.get("mode") or "hybrid"
    result = search.retrieve(
        principal,
        case.get("query") or "",
        limit=int(case.get("limit") or 8),
        max_chars=int(case.get("max_chars") or 4000),
        mode=mode,
        purpose="eval",
    )
    text = result.get("text") or ""
    matches = result.get("matches") or []
    citations = result.get("citations") or []
    ok = True
    reasons: list[str] = []

    if case.get("expect_denied"):
        if not result.get("denied") and (result.get("chars") or 0) > 0:
            ok = False
            reasons.append("expected_denied_or_empty")
    if case.get("expect_empty"):
        if (result.get("chars") or 0) > 0 or matches:
            ok = False
            reasons.append("expected_empty")
    if case.get("min_chars") and (result.get("chars") or 0) < int(case["min_chars"]):
        ok = False
        reasons.append(f"min_chars<{case['min_chars']}")
    if case.get("expect_any"):
        if not _contains_any(text, list(case["expect_any"])):
            # also check snippets
            blob = text + "\n" + "\n".join(m.get("snippet") or "" for m in matches)
            if not _contains_any(blob, list(case["expect_any"])):
                ok = False
                reasons.append("expect_any_miss")
    if case.get("expect_none"):
        blob = text + "\n" + "\n".join(m.get("snippet") or "" for m in matches)
        if _contains_any(blob, list(case["expect_none"])):
            ok = False
            reasons.append("expect_none_hit")
    if case.get("require_citation"):
        if not citations and not any(m.get("citation") for m in matches):
            ok = False
            reasons.append("missing_citation")
    if case.get("require_graph") and not (result.get("graph") or {}).get("entities"):
        # soft: only fail if explicitly required and graph enabled
        if (result.get("graph") or {}).get("skipped"):
            reasons.append("graph_skipped")
        else:
            ok = False
            reasons.append("missing_graph")

    return {
        "id": case.get("id"),
        "ok": ok,
        "reasons": reasons,
        "chars": result.get("chars"),
        "matches": len(matches),
        "citations": len(citations),
        "denied": bool(result.get("denied")),
        "search_mode": result.get("search_mode"),
        "graph_summary": (result.get("graph") or {}).get("summary"),
        "query": case.get("query"),
    }


def run_eval(repo, *, cases_path: Path | None = None) -> dict[str, Any]:
    cases = load_cases(cases_path)
    search = BrainSearch(repo)
    results = [run_case(search, c) for c in cases]
    passed = sum(1 for r in results if r["ok"])
    failed = [r for r in results if not r["ok"]]
    return {
        "ok": len(failed) == 0,
        "total": len(results),
        "passed": passed,
        "failed": len(failed),
        "pass_rate": round(passed / len(results), 3) if results else 0.0,
        "results": results,
        "failures": failed,
    }
