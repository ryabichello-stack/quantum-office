from pathlib import Path
import base64
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import office_gateway


def test_mail_send_denies_missing_or_foreign_tenant():
    client = TestClient(office_gateway.app)
    payload = {"tenant_id": "A", "tenant_slug": "a", "to": "x@example.com", "subject": "Hi", "body": "Hello", "provider": "yandex", "username": "a@example.com", "password": "secret", "dry_run": True}
    assert client.post("/api/mail/send", json=payload).status_code == 403
    assert client.post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "B"}).status_code == 403
    valid = client.post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "A"})
    assert valid.status_code == 200
    assert valid.json()["stub"] is True


def test_mail_probe_denies_foreign_tenant():
    client = TestClient(office_gateway.app)
    response = client.post("/api/mail/probe", json={"tenant_id": "A", "provider": "yandex", "username": "a@example.com", "password": "secret"}, headers={"X-Tenant-Id": "B"})
    assert response.status_code == 403


def test_attachment_accepts_any_file_from_same_tenant_request():
    client = TestClient(office_gateway.app)
    payload = {"tenant_id": "A", "tenant_slug": "a", "to": "x@example.com", "subject": "Hi", "body": "Hello", "provider": "yandex", "username": "a@example.com", "password": "secret", "dry_run": True, "attachment_name": "presentation.pdf", "attachment_base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode()}
    assert client.post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "B"}).status_code == 403
    assert client.post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "A"}).status_code == 200
    payload["attachment_name"] = "offer.xlsx"
    payload["attachment_base64"] = base64.b64encode(b"spreadsheet bytes").decode()
    assert client.post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "A"}).status_code == 200


def test_selected_attachment_is_in_sent_message(monkeypatch):
    from email import message_from_string

    seen = {}

    class SMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def login(self, username, password):
            pass

        def sendmail(self, sender, recipients, message):
            seen["message"] = message_from_string(message)

    monkeypatch.setattr(office_gateway.smtplib, "SMTP_SSL", SMTP)
    monkeypatch.setattr(office_gateway, "FORCE_DRY_RUN", False)
    payload = {"tenant_id": "A", "tenant_slug": "a", "to": "x@example.com", "subject": "Hi", "body": "Hello", "provider": "yandex", "username": "a@example.com", "password": "secret", "attachment_name": "offer.xlsx", "attachment_base64": base64.b64encode(b"spreadsheet bytes").decode()}
    response = TestClient(office_gateway.app).post("/api/mail/send", json=payload, headers={"X-Tenant-Id": "A"})
    assert response.status_code == 200
    assert response.json()["attached"] is True
    attachments = list(seen["message"].iter_attachments()) if hasattr(seen["message"], "iter_attachments") else [part for part in seen["message"].walk() if part.get_filename()]
    assert len(attachments) == 1
    assert attachments[0].get_filename() == "offer.xlsx"
    assert attachments[0].get_payload(decode=True) == b"spreadsheet bytes"
