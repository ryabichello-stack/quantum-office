"""Reject invalid credentials after the real Hermes positive smoke.

Runs only against the disposable gate1_lab_api SQLite database.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.agent_task import AgentRun
from app.models.tenant import Tenant


identities = json.loads(Path("/data/identities.json").read_text())
engine = create_engine("sqlite:////data/gate1.sqlite")
sessions = sessionmaker(bind=engine)
url = "http://delno-api:8020/v1/mcp/tools/call"
body = {"name": "get_tenant_summary", "arguments": {}}


def call(identity: dict) -> int:
    with httpx.Client(trust_env=False, timeout=5) as client:
        return client.post(url, headers={
            "Authorization": f"Bearer {identity['token']}",
            "X-Delno-Run-Id": identity["run_id"],
            "X-Delno-Profile-Id": identity["profile"],
        }, json=body).status_code


assert call(identities[0]) == 200
with sessions() as db:
    row = db.query(Tenant).filter(Tenant.id == UUID(identities[0]["tenant_id"])).one()
    settings = dict(row.settings)
    blob = dict(settings["hermes_nous"])
    grants = dict(blob["run_tokens"])
    for key, entry in grants.items():
        if entry.get("run_id") == identities[0]["run_id"]:
            grants[key] = {**entry, "expires_at": int(time.time()) - 1}
    blob["run_tokens"] = grants
    settings["hermes_nous"] = blob
    row.settings = settings
    db.commit()
assert call(identities[0]) == 401

assert call(identities[1]) == 200
with sessions() as db:
    row = db.query(AgentRun).filter(AgentRun.hermes_run_id == identities[1]["run_id"]).one()
    row.status = "completed"
    db.commit()
assert call(identities[1]) == 401

with httpx.Client(trust_env=False, timeout=5) as client:
    legacy = client.post(url, headers={"Authorization": f"Bearer {identities[0]['legacy_key']}"}, json=body)
    assert legacy.status_code == 403
    foreign = client.post(url, headers={
        "Authorization": f"Bearer {identities[2]['token']}",
        "X-Delno-Run-Id": identities[2]["run_id"],
        "X-Delno-Profile-Id": identities[0]["profile"],
    }, json=body)
    assert foreign.status_code == 403

print("gate1_negative_smoke_ok expired=401 completed=401 legacy=403 foreign_profile=403")
