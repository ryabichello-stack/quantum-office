from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import main


def test_send_requires_tenant_and_own_delivery_credentials():
    client = TestClient(main.app)
    payload = {"source": "yadisk", "path": "/proposal.pdf", "via": "email", "to": "x@example.com", "tenant_id": "A"}
    assert client.post("/api/files/send", json=payload).status_code == 403
    assert client.post("/api/files/send", json=payload, headers={"X-Tenant-Id": "B"}).status_code == 403
    assert client.post("/api/files/send", json=payload, headers={"X-Tenant-Id": "A"}).status_code == 403


def test_send_cannot_read_server_local_or_repo():
    client = TestClient(main.app)
    payload = {"source": "local", "path": "/etc/passwd", "via": "email", "to": "x@example.com", "tenant_id": "A", "credentials": {"token": "a"}, "delivery_credentials": {"username": "a"}}
    response = client.post("/api/files/send", json=payload, headers={"X-Tenant-Id": "A"})
    assert response.status_code == 403
