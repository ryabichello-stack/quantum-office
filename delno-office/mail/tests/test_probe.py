import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


spec = importlib.util.spec_from_file_location(
    "office_gateway", Path(__file__).resolve().parents[1] / "office_gateway.py"
)
gateway = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gateway)
client = TestClient(gateway.app)


def test_probe_uses_supplied_credentials_and_does_not_send(monkeypatch):
    seen = {}

    class SMTP:
        def __init__(self, host, port, timeout):
            seen.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password):
            seen.update(username=username, password=password)

    monkeypatch.setattr(gateway.smtplib, "SMTP_SSL", SMTP)
    response = client.post(
        "/api/mail/probe",
        json={"tenant_id": "tenant-a", "provider": "yandex", "username": "a@example.ru", "password": "private"},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert seen == {"host": "smtp.yandex.ru", "port": 465, "timeout": 8, "username": "a@example.ru", "password": "private"}
    assert "private" not in response.text


def test_probe_rejects_unknown_provider():
    response = client.post(
        "/api/mail/probe",
        json={"tenant_id": "tenant-a", "provider": "custom", "username": "a@example.ru", "password": "private"},
        headers={"X-Tenant-Id": "tenant-a"},
    )
    assert response.status_code == 400


def test_send_requires_tenant_credentials():
    response = client.post(
        "/api/mail/send",
        json={"to": "client@example.ru", "subject": "Test", "body": "Hello", "tenant_slug": "tenant-b"},
    )
    assert response.status_code == 403


def test_send_uses_only_request_tenant_account(monkeypatch):
    seen = {}

    class SMTP:
        def __init__(self, host, port, timeout):
            seen.update(host=host, port=port)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password):
            seen.update(username=username, password=password)

        def sendmail(self, sender, recipients, message):
            seen.update(sender=sender, recipients=recipients)

    monkeypatch.setattr(gateway.smtplib, "SMTP_SSL", SMTP)
    monkeypatch.setattr(gateway, "FORCE_DRY_RUN", False)
    response = client.post(
        "/api/mail/send",
        json={
            "tenant_slug": "tenant-b", "tenant_id": "b", "provider": "mailru",
            "username": "b@example.ru", "password": "tenant-b-secret",
            "to": "client@example.ru", "subject": "Test", "body": "Hello",
        },
        headers={"X-Tenant-Id": "b"},
    )
    assert response.status_code == 200
    assert response.json()["sent"] is True
    assert seen == {
        "host": "smtp.mail.ru", "port": 465, "username": "b@example.ru",
        "password": "tenant-b-secret", "sender": "b@example.ru", "recipients": ["client@example.ru"],
    }
    assert "tenant-b-secret" not in response.text
