"""YouTube Data API client skeleton — private uploads only (never auto-publish).

Env:
  YOUTUBE_UPLOAD_ENABLED=0|1
  YOUTUBE_CLIENT_SECRETS=/path/to/client_secret.json
  YOUTUBE_TOKEN_PATH=/path/to/token.json   (optional OAuth token cache)

Without secrets or google-api libraries, returns a queued stub (same as before).
Secrets paths must stay outside git (mode 600 on prod).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("ava-outreach.video_studio.youtube")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def upload_enabled() -> bool:
    return (os.getenv("YOUTUBE_UPLOAD_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def secrets_path() -> Path | None:
    raw = (os.getenv("YOUTUBE_CLIENT_SECRETS") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return p if p.is_file() else None


def token_path() -> Path:
    raw = (os.getenv("YOUTUBE_TOKEN_PATH") or "").strip()
    if raw:
        return Path(raw)
    secrets = secrets_path()
    if secrets:
        return secrets.with_name("youtube_token.json")
    return Path("/opt/ava-outreach/secrets/youtube_token.json")


class YouTubeClient:
    """Thin wrapper: status + private upload. Public publish is intentionally absent."""

    def status(self) -> dict[str, Any]:
        secrets = secrets_path()
        google_ok = False
        try:
            import googleapiclient.discovery  # noqa: F401
            import google_auth_oauthlib.flow  # noqa: F401

            google_ok = True
        except ImportError:
            google_ok = False
        return {
            "upload_enabled": upload_enabled(),
            "secrets_configured": bool(secrets),
            "secrets_path": str(secrets) if secrets else None,
            "token_path": str(token_path()),
            "google_libs": google_ok,
            "default_visibility": "private",
            "auto_publish": False,
        }

    def upload_private(
        self,
        *,
        title: str,
        description: str = "",
        file_path: str | Path | None = None,
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        """Upload as private, or return stub queue result.

        Never sets privacyStatus=public. Real bytes upload only when
        YOUTUBE_UPLOAD_ENABLED + secrets + google libs + file_path exist.
        """
        st = self.status()
        if not st["upload_enabled"]:
            return {
                "ok": True,
                "mode": "stub",
                "visibility": "private",
                "youtube_id": f"private-pending-{(draft_id or 'draft')[:8]}",
                "note": "YOUTUBE_UPLOAD_ENABLED=false — queue stub only",
            }

        if not st["secrets_configured"] or not st["google_libs"]:
            return {
                "ok": True,
                "mode": "stub_queued",
                "visibility": "private",
                "youtube_id": f"private-pending-{(draft_id or 'draft')[:8]}",
                "note": (
                    "Очередь принята. Нужны YOUTUBE_CLIENT_SECRETS + "
                    "google-api-python-client / google-auth-oauthlib для реального upload."
                ),
                "status": st,
            }

        path = Path(file_path) if file_path else None
        if not path or not path.is_file():
            return {
                "ok": True,
                "mode": "stub_queued",
                "visibility": "private",
                "youtube_id": f"private-pending-{(draft_id or 'draft')[:8]}",
                "note": "Секреты есть, но нет media file_path — очередь без байтов",
                "status": st,
            }

        try:
            youtube_id = self._upload_bytes(
                path=path,
                title=(title or "Untitled")[:100],
                description=(description or "")[:5000],
            )
            return {
                "ok": True,
                "mode": "uploaded",
                "visibility": "private",
                "youtube_id": youtube_id,
                "note": "Uploaded as private (YouTube Data API)",
            }
        except Exception as exc:  # noqa: BLE001
            logger.exception("youtube upload failed")
            return {
                "ok": False,
                "error": str(exc)[:300],
                "visibility": "private",
                "status": st,
            }

    def _build_service(self) -> Any:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        secrets = secrets_path()
        assert secrets is not None
        tok = token_path()
        creds = None
        if tok.is_file():
            creds = Credentials.from_authorized_user_file(str(tok), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # Headless prod: expect pre-authorized token.json; interactive flow for local only
                flow = InstalledAppFlow.from_client_secrets_file(str(secrets), SCOPES)
                creds = flow.run_local_server(port=0)
            tok.parent.mkdir(parents=True, exist_ok=True)
            tok.write_text(creds.to_json(), encoding="utf-8")
            try:
                os.chmod(tok, 0o600)
            except OSError:
                pass
        return build("youtube", "v3", credentials=creds)

    def _upload_bytes(self, *, path: Path, title: str, description: str) -> str:
        from googleapiclient.http import MediaFileUpload

        youtube = self._build_service()
        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
            },
        }
        media = MediaFileUpload(str(path), resumable=True)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _status, response = request.next_chunk()
        return str(response.get("id") or "")
