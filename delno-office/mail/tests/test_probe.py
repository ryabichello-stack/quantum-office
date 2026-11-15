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
    )
    assert response.status_code == 200
    assert response.json()["status"] == "connected"
    assert seen == {"host": "smtp.yandex.ru", "port": 465, "timeout": 8, "username": "a@example.ru", "password": "private"}
    assert "private" not in response.text


def test_probe_rejects_unknown_provider():
    response = client.post(
        "/api/mail/probe",
        json={"tenant_id": "tenant-a", "provider": "custom", "username": "a@example.ru", "password": "private"},
    )
    assert response.status_code == 400
