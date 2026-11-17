from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import main


def test_create_rejects_missing_or_foreign_tenant():
    client = TestClient(main.app)
    missing = client.post("/api/conferences", json={"title": "A", "provider": "jitsi"})
    foreign = client.post("/api/conferences", json={"tenant_id": "A", "provider": "jitsi"}, headers={"X-Tenant-Id": "B"})
    assert missing.status_code == 422
    assert foreign.status_code == 403


def test_create_rejects_global_credentials_and_invites():
    client = TestClient(main.app)
    headers = {"X-Tenant-Id": "A"}
    missing_token = client.post("/api/conferences", json={"tenant_id": "A", "provider": "yandex"}, headers=headers)
    global_invites = client.post("/api/conferences", json={"tenant_id": "A", "provider": "jitsi", "send_invites": True, "invitees": ["x@example.com"]}, headers=headers)
    assert missing_token.status_code == 403
    assert global_invites.status_code == 403


def test_jitsi_is_tenant_bound():
    client = TestClient(main.app)
    response = client.post("/api/conferences", json={"tenant_id": "A", "provider": "jitsi", "title": "Встреча"}, headers={"X-Tenant-Id": "A"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["stub"] is False
