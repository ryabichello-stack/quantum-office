"""File sources: local, github repo, Yandex Disk, Mail.ru Cloud."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import xml.etree.ElementTree as ET
import urllib.error
import urllib.parse
import urllib.request
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

from allowlist import default_local_allowlist, parse_allowlist, resolve_under_allowlist
from models import FetchedFile, ListedEntry, SourceError

logger = logging.getLogger(__name__)

GITHUB_REPO = os.getenv("FILES_GITHUB_REPO", "ryabichello-stack/quantum-office").strip()
GITHUB_REF = os.getenv("FILES_GITHUB_REF", "main").strip()
GITHUB_TOKEN = os.getenv("FILES_GITHUB_TOKEN", "").strip()

YADISK_TOKEN = os.getenv("YADISK_TOKEN", "").strip()
YADISK_API = "https://cloud-api.yandex.net/v1/disk"

# Mail.ru Cloud WebDAV — same mailbox as SMTP/CalDAV when dedicated vars are empty.
MAILRU_WEBDAV_URL = (
    os.getenv("MAILRU_WEBDAV_URL", "").strip() or "https://webdav.cloud.mail.ru"
).rstrip("/")
MAILRU_WEBDAV_USER = (
    os.getenv("MAILRU_WEBDAV_USER", "").strip()
    or os.getenv("MAIL_USERNAME", "").strip()
    or os.getenv("MAILRU_CALDAV_USERNAME", "").strip()
)
MAILRU_WEBDAV_PASSWORD = (
    os.getenv("MAILRU_WEBDAV_PASSWORD", "").strip()
    or os.getenv("MAIL_PASSWORD", "").strip()
    or os.getenv("MAILRU_CALDAV_PASSWORD", "").strip()
)

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


def _mailru_auth_header() -> str:
    token = base64.b64encode(
        f"{MAILRU_WEBDAV_USER}:{MAILRU_WEBDAV_PASSWORD}".encode()
    ).decode()
    return f"Basic {token}"


def _mailru_url(path: str) -> str:
    """Build WebDAV URL; encode each segment, keep slashes."""
    clean = path if path.startswith("/") else f"/{path}"
    parts = [urllib.parse.quote(p, safe="") for p in clean.split("/") if p != ""]
    return MAILRU_WEBDAV_URL + "/" + "/".join(parts) if parts else MAILRU_WEBDAV_URL + "/"


def fetch_mailru(path: str) -> FetchedFile:
    if not (MAILRU_WEBDAV_USER and MAILRU_WEBDAV_PASSWORD):
        raise SourceError(
            "mailru_not_configured",
            "Set MAILRU_WEBDAV_USER/PASSWORD (or MAIL_USERNAME/MAIL_PASSWORD) in .env",
        )
    clean = path if path.startswith("/") else f"/{path}"
    url = _mailru_url(clean)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": _mailru_auth_header(),
            "User-Agent": "ava-files/mailru-webdav",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceError("mailru_http_error", f"Mail.ru Cloud {exc.code}: {body}") from exc
    except Exception as exc:
        raise SourceError("mailru_error", str(exc)) from exc

    filename = Path(clean).name or "file.bin"
    data = _read_limited(raw, clean)
    return FetchedFile(
        filename=filename,
        content=data,
        content_type=_guess_type(filename),
        source="mailru",
        path=clean,
    )


def _normalize_dir_path(path: str) -> str:
    clean = (path or "/").strip() or "/"
    if not clean.startswith("/"):
        clean = "/" + clean
    # Keep root as "/", other dirs without trailing slash for stable paths
    if clean != "/":
        clean = clean.rstrip("/")
    return clean


def _webdav_href_to_path(href: str) -> str:
    """Convert WebDAV href (absolute or relative) to cloud path starting with /."""
    raw = (href or "").strip()
    if not raw:
        return "/"
    parsed = urllib.parse.urlparse(raw)
    path = urllib.parse.unquote(parsed.path or raw)
    # Strip webdav root prefix if present
    for prefix in ("/webdav",):
        if path.startswith(prefix + "/") or path == prefix:
            path = path[len(prefix) :] or "/"
    if not path.startswith("/"):
        path = "/" + path
    if path != "/":
        path = path.rstrip("/")
    return path or "/"


def _normalize_dav_datetime(raw: Optional[str]) -> Optional[str]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        pass
    # ISO-like: 2024-01-02T15:04:05Z / +03:00
    if "T" in text:
        return text.replace("Z", "").split("+")[0][:19].replace("T", " ") + " UTC"
    return text


def _prop_text(prop: Optional[ET.Element], tag: str, ns: dict[str, str]) -> Optional[str]:
    if prop is None:
        return None
    el = prop.find(tag, ns)
    if el is None or not (el.text or "").strip():
        return None
    return (el.text or "").strip()


def list_mailru(path: str = "/") -> list[ListedEntry]:
    """List one directory level on Mail.ru Cloud via WebDAV PROPFIND Depth:1."""
    if not (MAILRU_WEBDAV_USER and MAILRU_WEBDAV_PASSWORD):
        raise SourceError(
            "mailru_not_configured",
            "Set MAILRU_WEBDAV_USER/PASSWORD (or MAIL_USERNAME/MAIL_PASSWORD) in .env",
        )
    clean = _normalize_dir_path(path)
    # WebDAV collections usually want a trailing slash
    list_path = clean if clean.endswith("/") else clean + "/"
    url = _mailru_url(list_path)
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:">'
        "<d:prop>"
        "<d:resourcetype/><d:displayname/><d:getcontentlength/>"
        "<d:getlastmodified/><d:creationdate/>"
        "</d:prop>"
        "</d:propfind>"
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="PROPFIND",
        headers={
            "Authorization": _mailru_auth_header(),
            "User-Agent": "ava-files/mailru-webdav",
            "Depth": "1",
            "Content-Type": "application/xml; charset=utf-8",
            "Accept": "application/xml, text/xml, */*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            xml_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        raise SourceError("mailru_http_error", f"Mail.ru Cloud {exc.code}: {err}") from exc
    except Exception as exc:
        raise SourceError("mailru_error", str(exc)) from exc

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise SourceError("mailru_xml_error", f"bad PROPFIND xml: {exc}") from exc

    ns = {"d": "DAV:"}
    self_path = _normalize_dir_path(clean)
    entries: list[ListedEntry] = []
    seen: set[str] = set()
    for resp_el in root.findall(".//d:response", ns):
        href_el = resp_el.find("d:href", ns)
        if href_el is None or not (href_el.text or "").strip():
            continue
        entry_path = _webdav_href_to_path(href_el.text or "")
        if _normalize_dir_path(entry_path) == self_path:
            continue
        prop = resp_el.find("d:propstat/d:prop", ns)
        if prop is None:
            prop = resp_el.find(".//d:prop", ns)
        is_dir = False
        size: Optional[int] = None
        display = Path(entry_path).name or entry_path
        modified_at = None
        created_at = None
        if prop is not None:
            rt = prop.find("d:resourcetype", ns)
            if rt is not None and rt.find("d:collection", ns) is not None:
                is_dir = True
            dn = prop.find("d:displayname", ns)
            if dn is not None and (dn.text or "").strip():
                display = (dn.text or "").strip()
            cl = prop.find("d:getcontentlength", ns)
            if cl is not None and (cl.text or "").strip().isdigit():
                size = int(cl.text or "0")
            modified_at = _normalize_dav_datetime(_prop_text(prop, "d:getlastmodified", ns))
            created_at = _normalize_dav_datetime(_prop_text(prop, "d:creationdate", ns))
        # Trailing slash in href often means directory
        if (href_el.text or "").rstrip().endswith("/"):
            is_dir = True
        key = f"{'dir' if is_dir else 'file'}:{entry_path}"
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            ListedEntry(
                name=display,
                path=entry_path if entry_path.startswith("/") else f"/{entry_path}",
                type="dir" if is_dir else "file",
                bytes=None if is_dir else size,
                modified_at=modified_at,
                created_at=created_at,
            )
        )

    entries.sort(key=lambda e: (0 if e.type == "dir" else 1, e.name.lower()))
    return entries


def list_local(path: str = "/") -> list[ListedEntry]:
    """List allowlisted local directory (one level)."""
    allow = default_local_allowlist()
    raw = (path or "").strip() or str(allow[0])
    try:
        # For listing, allow directory roots from allowlist
        if raw in ("/", ".", ""):
            resolved = allow[0].resolve()
        else:
            resolved = resolve_under_allowlist(raw, allow)
    except ValueError as exc:
        raise SourceError(str(exc), f"local path not allowed: {path}") from exc
    if resolved.is_file():
        st = resolved.stat()
        return [
            ListedEntry(
                name=resolved.name,
                path=str(resolved),
                type="file",
                bytes=st.st_size,
                modified_at=_fs_mtime(st.st_mtime),
                created_at=_fs_mtime(getattr(st, "st_ctime", st.st_mtime)),
            )
        ]
    if not resolved.is_dir():
        raise SourceError("not_found", f"local dir not found: {resolved}")
    entries: list[ListedEntry] = []
    for child in sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if child.name.startswith("."):
            continue
        st = child.stat()
        entries.append(
            ListedEntry(
                name=child.name,
                path=str(child.resolve()),
                type="dir" if child.is_dir() else "file",
                bytes=None if child.is_dir() else st.st_size,
                modified_at=_fs_mtime(st.st_mtime),
                created_at=_fs_mtime(getattr(st, "st_ctime", st.st_mtime)),
            )
        )
    return entries


def _fs_mtime(ts: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def list_yadisk(path: str = "/") -> list[ListedEntry]:
    if not YADISK_TOKEN:
        raise SourceError("yadisk_not_configured", "Set YADISK_TOKEN in .env")
    disk_path = path if path.startswith("disk:") or path.startswith("/") else f"/{path}"
    if not disk_path.startswith("disk:"):
        disk_path = f"disk:{disk_path}"
    meta_url = (
        f"{YADISK_API}/resources?"
        + urllib.parse.urlencode({"path": disk_path, "limit": 200})
    )
    headers = {"Authorization": f"OAuth {YADISK_TOKEN}", "Accept": "application/json"}
    req = urllib.request.Request(meta_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:300]
        raise SourceError("yadisk_http_error", f"Yandex Disk {exc.code}: {body}") from exc

    items = ((meta.get("_embedded") or {}).get("items")) or []
    entries: list[ListedEntry] = []
    for item in items:
        itype = "dir" if item.get("type") == "dir" else "file"
        ipath = item.get("path") or ""
        # disk:/Folder/file → /Folder/file
        if ipath.startswith("disk:"):
            ipath = ipath[5:] or "/"
        entries.append(
            ListedEntry(
                name=str(item.get("name") or Path(ipath).name),
                path=ipath if ipath.startswith("/") else f"/{ipath}",
                type=itype,  # type: ignore[arg-type]
                bytes=None if itype == "dir" else item.get("size"),
                modified_at=_normalize_dav_datetime(item.get("modified")),
                created_at=_normalize_dav_datetime(item.get("created")),
            )
        )
    entries.sort(key=lambda e: (0 if e.type == "dir" else 1, e.name.lower()))
    return entries


def list_entries(source: str, path: str = "/") -> list[ListedEntry]:
    source = (source or "").strip().lower()
    if source == "local":
        return list_local(path)
    if source in ("yadisk", "yandex", "yandex_disk"):
        return list_yadisk(path)
    if source in ("mailru", "mailru_disk", "cloud_mail"):
        return list_mailru(path)
    raise SourceError("unknown_source", f"list unsupported for source: {source}")


def search_mailru(
    query: str,
    *,
    path: str = "/",
    limit: int = 40,
    max_dirs: int = 80,
) -> list[ListedEntry]:
    """BFS name search under path (Mail.ru has no dedicated search API over WebDAV)."""
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise SourceError("query_too_short", "query must be at least 2 characters")
    limit = max(1, min(int(limit or 40), 100))
    max_dirs = max(1, min(int(max_dirs or 80), 200))
    start = _normalize_dir_path(path)
    queue: list[str] = [start]
    visited: set[str] = set()
    hits: list[ListedEntry] = []
    while queue and len(hits) < limit and len(visited) < max_dirs:
        cur = queue.pop(0)
        if cur in visited:
            continue
        visited.add(cur)
        try:
            children = list_mailru(cur)
        except SourceError:
            continue
        for e in children:
            hay = f"{e.name} {e.path}".lower()
            if q in hay:
                hits.append(e)
                if len(hits) >= limit:
                    break
            if e.type == "dir":
                queue.append(e.path)
    return hits


def search_local(query: str, *, path: str = "/", limit: int = 40) -> list[ListedEntry]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise SourceError("query_too_short", "query must be at least 2 characters")
    allow = default_local_allowlist()
    raw = (path or "").strip() or str(allow[0])
    try:
        root = allow[0].resolve() if raw in ("/", ".", "") else resolve_under_allowlist(raw, allow)
    except ValueError as exc:
        raise SourceError(str(exc), f"local path not allowed: {path}") from exc
    if not root.is_dir():
        raise SourceError("not_found", f"local dir not found: {root}")
    hits: list[ListedEntry] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        base = Path(dirpath)
        for name, is_dir in [(d, True) for d in dirnames] + [(f, False) for f in filenames]:
            if q not in name.lower():
                continue
            full = (base / name).resolve()
            st = full.stat()
            hits.append(
                ListedEntry(
                    name=name,
                    path=str(full),
                    type="dir" if is_dir else "file",
                    bytes=None if is_dir else st.st_size,
                    modified_at=_fs_mtime(st.st_mtime),
                    created_at=_fs_mtime(getattr(st, "st_ctime", st.st_mtime)),
                )
            )
            if len(hits) >= limit:
                return hits
    return hits


def search_yadisk(query: str, *, limit: int = 40) -> list[ListedEntry]:
    if not YADISK_TOKEN:
        raise SourceError("yadisk_not_configured", "Set YADISK_TOKEN in .env")
    q = (query or "").strip()
    if len(q) < 2:
        raise SourceError("query_too_short", "query must be at least 2 characters")
    url = (
        f"{YADISK_API}/resources/files?"
        + urllib.parse.urlencode({"limit": max(1, min(limit, 100))})
    )
    # Prefer dedicated search when available
    search_url = (
        f"{YADISK_API}/search?"
        + urllib.parse.urlencode({"query": q, "limit": max(1, min(limit, 100))})
    )
    headers = {"Authorization": f"OAuth {YADISK_TOKEN}", "Accept": "application/json"}
    items = []
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        items = meta.get("items") or ((meta.get("_embedded") or {}).get("items")) or []
    except urllib.error.HTTPError:
        # Fallback: list recent files and filter by name
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            meta = json.loads(resp.read().decode("utf-8"))
        items = [
            it
            for it in (meta.get("items") or [])
            if q.lower() in str(it.get("name") or "").lower()
        ]
    entries: list[ListedEntry] = []
    for item in items[:limit]:
        itype = "dir" if item.get("type") == "dir" else "file"
        ipath = item.get("path") or ""
        if ipath.startswith("disk:"):
            ipath = ipath[5:] or "/"
        entries.append(
            ListedEntry(
                name=str(item.get("name") or Path(ipath).name),
                path=ipath if ipath.startswith("/") else f"/{ipath}",
                type=itype,  # type: ignore[arg-type]
                bytes=None if itype == "dir" else item.get("size"),
                modified_at=_normalize_dav_datetime(item.get("modified")),
                created_at=_normalize_dav_datetime(item.get("created")),
            )
        )
    return entries


def search_entries(
    source: str,
    query: str,
    *,
    path: str = "/",
    limit: int = 40,
) -> list[ListedEntry]:
    source = (source or "").strip().lower()
    if source == "local":
        return search_local(query, path=path, limit=limit)
    if source in ("yadisk", "yandex", "yandex_disk"):
        return search_yadisk(query, limit=limit)
    if source in ("mailru", "mailru_disk", "cloud_mail"):
        return search_mailru(query, path=path, limit=limit)
    raise SourceError("unknown_source", f"search unsupported for source: {source}")


def entry_to_dict(e: ListedEntry) -> dict:
    return {
        "name": e.name,
        "path": e.path,
        "type": e.type,
        "bytes": e.bytes,
        "modified_at": e.modified_at,
        "created_at": e.created_at,
    }


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
        "mailru_webdav_url": MAILRU_WEBDAV_URL,
        "mailru_user": MAILRU_WEBDAV_USER or None,
        "list_sources": ["mailru", "yadisk", "local"],
        "max_bytes": MAX_BYTES,
    }
