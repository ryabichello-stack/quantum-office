"""RBAC, owned-listen, YouTube client skeleton."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from modules.rbac import (
    Principal,
    enforce_request,
    permission_for_request,
    resolve_principal,
)
from modules.radar.owned_listen import poll_owned_pages
from modules.video_studio import VideoStudioStore
from modules.video_studio.youtube_client import YouTubeClient


def test_permission_for_request_reads_are_none():
    assert permission_for_request("GET", "/api/modules/social/capabilities") is None
    assert permission_for_request("POST", "/send-batch") == "outreach.send"
    assert permission_for_request("PUT", "/api/settings") == "outreach.settings"
    assert permission_for_request("POST", "/api/modules/radar/owned/poll") == "studio.write"
    assert permission_for_request("POST", "/api/v1/tenants/bootstrap") == "admin"


def test_viewer_blocked_on_send():
    p = Principal(role="viewer")
    try:
        enforce_request(p, "POST", "/send-one")
        assert False, "expected 403"
    except Exception as exc:  # HTTPException
        assert getattr(exc, "status_code", None) == 403


def test_ops_can_studio_not_admin():
    p = Principal(role="ops")
    enforce_request(p, "POST", "/api/modules/content_studio/drafts")
    try:
        enforce_request(p, "POST", "/api/v1/tenants/bootstrap")
        assert False, "expected 403"
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403


def test_resolve_principal_rbac_off_is_owner(monkeypatch):
    monkeypatch.delenv("OUTREACH_RBAC_ENABLED", raising=False)
    assert resolve_principal("anything").role == "owner"


def test_resolve_principal_role_tokens(monkeypatch):
    monkeypatch.setenv("OUTREACH_RBAC_ENABLED", "1")
    monkeypatch.setenv("OUTREACH_UI_TOKEN", "primary-secret")
    monkeypatch.setenv("OUTREACH_UI_ROLE", "owner")
    monkeypatch.setenv("OUTREACH_ROLE_TOKENS", "ops:ops-secret,viewer:view-secret")
    assert resolve_principal("primary-secret").role == "owner"
    assert resolve_principal("ops-secret").role == "ops"
    assert resolve_principal("view-secret").role == "viewer"


def test_owned_listen_disabled():
    with patch.dict(os.environ, {"OWNED_LISTEN_ENABLED": "0"}, clear=False):
        out = poll_owned_pages()
        assert out["ok"] is True
        assert out["enabled"] is False
        assert out["ingested"] == 0


def test_owned_listen_stub_ingest(monkeypatch):
    monkeypatch.setenv("OWNED_LISTEN_ENABLED", "1")
    monkeypatch.setenv("OWNED_TG_CHANNELS", "@ql_news")
    monkeypatch.setenv("OWNED_VK_GROUPS", "ql_group")
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "m.db"
        with patch("modules.radar.RadarStore") as RS:
            store = type("S", (), {})()
            ingested = []

            def ingest(**kwargs):
                ingested.append(kwargs)
                return {"id": "x", **kwargs}

            store.ingest = ingest
            RS.return_value = store
            out = poll_owned_pages(dry_run=False)
            assert out["ok"] is True
            assert out["ingested"] == 2
            assert ingested[0]["source"] == "owned_telegram"
            assert out["auto_outreach"] is False


def test_youtube_client_stub_status():
    st = YouTubeClient().status()
    assert st["default_visibility"] == "private"
    assert st["auto_publish"] is False


def test_video_queue_uses_youtube_client():
    with tempfile.TemporaryDirectory() as tmp:
        store = VideoStudioStore(Path(tmp) / "v.db")
        draft = store.create_draft(title="T", brief="B")
        store.set_status(draft["id"], "approved")
        with patch.dict(os.environ, {"YOUTUBE_UPLOAD_ENABLED": "0"}, clear=False):
            out = store.queue_private_upload(draft["id"])
        assert out["ok"] is True
        assert out["visibility"] == "private"
        assert out["draft"]["status"] == "uploaded_private"
