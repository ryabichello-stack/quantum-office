"""API v1 facade, Bitrix lead adapter, cluster merge, tenant bootstrap."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.social import SocialStore
from tenant_bootstrap import bootstrap_tenant, list_tenants


def test_cluster_merge_keeps_one():
    with tempfile.TemporaryDirectory() as tmp:
        store = SocialStore(Path(tmp) / "m.db")
        out = store.run_search(
            sources=["web_import"],
            imports=[
                {
                    "source": "web_import",
                    "full_name": "Анна Ким",
                    "profile_url": "https://a.example/1",
                },
                {
                    "source": "web_import",
                    "full_name": "Анна  Ким",
                    "profile_url": "https://a.example/2",
                },
            ],
        )
        clustered = [c for c in out["candidates"] if c.get("cluster_id")]
        assert len(clustered) >= 2
        cid = clustered[0]["cluster_id"]
        keep = clustered[0]["id"]
        merged = store.merge_cluster(cid, keep_candidate_id=keep)
        assert merged["ok"]
        assert merged["merged_count"] >= 1
        statuses = {
            c["id"]: c["status"]
            for c in store.list_candidates(run_id=out["run"]["id"])
        }
        assert statuses[keep] == "approved"
        assert any(s == "merged" for s in statuses.values())


def test_tenant_bootstrap_copies_seed(tmp_path: Path, monkeypatch):
    # use real seed under outreach/config
    out = bootstrap_tenant("demo-tenant-x")
    assert out["ok"]
    assert "demo-tenant-x" in list_tenants()
    # cleanup
    import shutil
    from tenant_bootstrap import TENANTS_ROOT

    shutil.rmtree(TENANTS_ROOT / "demo-tenant-x", ignore_errors=True)


def test_bitrix_lead_dry_run():
    from bitrix_leads import sync_lead_to_bitrix

    out = sync_lead_to_bitrix(
        {"id": "l1", "account_id": None, "person_id": None, "source": "test", "status": "NEW"},
        dry_run=True,
    )
    assert out["ok"] and out["dry_run"]


def test_api_v1_health_mount(monkeypatch, tmp_path):
    import os

    os.environ["OUTREACH_UI_TOKEN"] = "test-token-xyz"
    monkeypatch.setenv("OUTREACH_UI_TOKEN", "test-token-xyz")
    # lightweight app with only v1
    from api_v1 import build_v1_router

    app = FastAPI()

    async def ok_auth():
        return None

    app.include_router(build_v1_router(require_auth=ok_auth))
    c = TestClient(app)
    r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["api"] == "v1"
