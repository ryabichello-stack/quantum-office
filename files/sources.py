"""File sources: local, github repo, Yandex Disk, Mail.ru Cloud."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

from allowlist import default_local_allowlist, parse_allowlist, resolve_under_allowlist
from models import FetchedFile, SourceError

logger = logging.getLogger(__name__)

GITHUB_REPO = os.getenv("FILES_GITHUB_REPO", "ryabichello-stack/quantum-office").strip()
GITHUB_REF = os.getenv("FILES_GITHUB_REF", "main").strip()
GITHUB_TOKEN = os.getenv("FILES_GITHUB_TOKEN", "").strip()

YADISK_TOKEN = os.getenv("YADISK_TOKEN", "").strip()
YADISK_API = "https://cloud-api.yandex.net/v1/disk"

MAILRU_WEBDAV_URL = os.getenv("MAILRU_WEBDAV_URL", "https://webdav.cloud.mail.ru").rstrip("/")
MAILRU_WEBDAV_USER = os.getenv("MAILRU_WEBDAV_USER", "").strip()
MAILRU_WEBDAV_PASSWORD = os.getenv("MAILRU_WEBDAV_PASSWORD", "").strip()

MAX_BYTES = int(os.getenv("FILES_MAX_BYTES", str(45 * 1024 * 1024)) or str(45 * 1024 * 1024))


def _guess_type(name: str) -> str:
    ctype, _ = mimetypes.guess_type(name)
    return ctype or "application/octet-stream"


def _read_limited(data: bytes, path: str) -> bytes:
    if len(data) > MAX_BYTES:
        raise SourceError("file_too_large", f"{path} exceeds FILES_MAX_BYTES={MAX_BYTES}")
    return data


def fetch_local(path: str) -> FetchedFile:
    allow = default_local_allowlist()
    try:
        resolved = resolve_under_allowlist(path, allow)
    except ValueError as exc:
        raise SourceError(str(exc), f"local path not allowed: {path}") from exc
    if not resolved.is_file():
        raise SourceError("not_found", f"local file not found: {resolved}")
    data = _read_limited(resolved.read_bytes(), str(resolved))
    return FetchedFile(
        filename=resolved.name,
        content=data,
        content_type=_guess_type(resolved.name),
        source="local",
        path=str(resolved),
    )


def fetch_repo(path: str, *, ref: Optional[str] = None, repo: Optional[str] = None) -> FetchedFile:
    """Fetch a file from GitHub repo via Contents API / raw."""
    repo = (repo or GITHUB_REPO).strip()
    ref = (ref or GITHUB_REF).strip()
    clean = path.lstrip("/")
    if ".." in Path(clean).parts:
        raise SourceError("path_not_allowed", "repo path traversal denied")

    api_url = f"https://api.github.com/repos/{repo}/contents/{urllib.parse.quote(clean)}?ref={urllib.parse.quote(ref)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ava-files",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"

    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceError("repo_http_error", f"GitHub {exc.code}: {body}") from exc
    except Exception as exc:
        raise SourceError("repo_error", str(exc)) from exc

    if meta.get("type") != "file":
        raise SourceError("not_a_file", f"path is not a file: {clean}")

    filename = meta.get("name") or Path(clean).name
    if meta.get("encoding") == "base64" and meta.get("content"):
        raw = base64.b64decode(meta["content"])
    elif meta.get("download_url"):
        dreq = urllib.request.Request(meta["download_url"], headers=headers)
        with urllib.request.urlopen(dreq, timeout=60) as dresp:
            raw = dresp.read()
    else:
        raise SourceError("repo_empty", "no content in GitHub response")

    data = _read_limited(raw, clean)
    return FetchedFile(
        filename=filename,
        content=data,
        content_type=_guess_type(filename),
        source="repo",
        path=f"{repo}@{ref}:{clean}",
    )


def fetch_yadisk(path: str) -> FetchedFile:
    if not YADISK_TOKEN:
        raise SourceError("yadisk_not_configured", "Set YADISK_TOKEN in .env")
    # Normalize to disk path
    disk_path = path if path.startswith("disk:") or path.startswith("/") else f"/{path}"
    if not disk_path.startswith("disk:"):
        disk_path = f"disk:{disk_path}"

    meta_url = (
        f"{YADISK_API}/resources/download?"
        + urllib.parse.urlencode({"path": disk_path})
    )
    headers = {"Authorization": f"OAuth {YADISK_TOKEN}", "Accept": "application/json"}
    req = urllib.request.Request(meta_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            href = json.loads(resp.read().decode("utf-8")).get("href")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceError("yadisk_http_error", f"Yandex Disk {exc.code}: {body}") from exc

    if not href:
        raise SourceError("yadisk_no_href", "download href missing")

    with urllib.request.urlopen(href, timeout=120) as resp:
        raw = resp.read()
    filename = Path(urllib.parse.unquote(disk_path.split(":")[-1])).name or "file.bin"
    data = _read_limited(raw, disk_path)
    return FetchedFile(
        filename=filename,
        content=data,
        content_type=_guess_type(filename),
        source="yadisk",
        path=disk_path,
    )


def fetch_mailru(path: str) -> FetchedFile:
    if not (MAILRU_WEBDAV_USER and MAILRU_WEBDAV_PASSWORD):
        raise SourceError(
            "mailru_not_configured",
            "Set MAILRU_WEBDAV_USER and MAILRU_WEBDAV_PASSWORD in .env",
        )
    clean = path if path.startswith("/") else f"/{path}"
    url = f"{MAILRU_WEBDAV_URL}{urllib.parse.quote(clean)}"
    auth = base64.b64encode(f"{MAILRU_WEBDAV_USER}:{MAILRU_WEBDAV_PASSWORD}".encode()).decode()
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceError("mailru_http_error", f"Mail.ru Cloud {exc.code}: {body}") from exc

    filename = Path(clean).name or "file.bin"
    data = _read_limited(raw, clean)
    return FetchedFile(
        filename=filename,
        content=data,
        content_type=_guess_type(filename),
        source="mailru",
        path=clean,
    )


def fetch(source: str, path: str, **kwargs) -> FetchedFile:
    source = (source or "").strip().lower()
    if source == "local":
        return fetch_local(path)
    if source in ("repo", "github"):
        return fetch_repo(path, ref=kwargs.get("ref"), repo=kwargs.get("repo"))
    if source in ("yadisk", "yandex", "yandex_disk"):
        return fetch_yadisk(path)
    if source in ("mailru", "mailru_disk", "cloud_mail"):
        return fetch_mailru(path)
    raise SourceError("unknown_source", f"unsupported source: {source}")


def sources_status() -> dict:
    return {
        "local_allowlist": [str(p) for p in default_local_allowlist()],
        "github_repo": GITHUB_REPO,
        "github_ref": GITHUB_REF,
        "github_token_set": bool(GITHUB_TOKEN),
        "yadisk_configured": bool(YADISK_TOKEN),
        "mailru_configured": bool(MAILRU_WEBDAV_USER and MAILRU_WEBDAV_PASSWORD),
        "max_bytes": MAX_BYTES,
    }
