from office_gateway import app, smtp_configured
from fastapi.testclient import TestClient


client = TestClient(app)


def test_health_tools_first():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["service"] == "delno-mail"
    assert body["creds_policy"] == "tools_first"


def test_send_dry_run_without_smtp(monkeypatch):
    monkeypatch.setenv("MAIL_SMTP_HOST", "")
    # re-import values are module-level — call endpoint which checks smtp_configured()
    r = client.post(
        "/api/mail/send",
        json={"to": "a@b.ru", "subject": "Hi", "body": "Hello", "tenant_slug": "demo"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stub"] is True
    assert body["dry_run"] is True
    assert body["sent"] is False
