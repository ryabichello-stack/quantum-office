"""Per-industry presentation PDF storage and resolution.

Priority when attaching to mail:
1. Uploaded override: ``$DATA_DIR/presentations/<pack_id>.pdf``
2. Pack asset slot: ``assets/presentations/<pack_id>.pdf``
3. Explicit settings path (``OUTREACH_PRESENTATION_PDF``)
4. Shared default: ``assets/quantum_payouts_presentation_small.pdf``
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

ASSETS_DIR = Path(__file__).resolve().parent / "assets"
PACK_ASSETS_DIR = ASSETS_DIR / "presentations"
DEFAULT_PRESENTATION = ASSETS_DIR / "quantum_payouts_presentation_small.pdf"

_PACK_ID_RE = re.compile(r"^[a-z0-9_]{1,64}$")


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "/opt/ava-outreach/data"))


def _custom_dir() -> Path:
    return _data_dir() / "presentations"


def normalize_pack_id(pack_id: str | None) -> str:
    raw = (pack_id or "").strip().lower().replace("-", "_")
    aliases = {
        "trade-in": "trade_in",
        "lombard": "lombards",
        "pawnshop": "lombards",
        "pawnshops": "lombards",
        "scrap_metal": "scrap",
        "metal": "scrap",
        "taxi": "gig",
        "couriers": "gig",
    }
    return aliases.get(raw, raw)


def assert_pack_id(pack_id: str | None) -> str:
    pid = normalize_pack_id(pack_id)
    if not pid or not _PACK_ID_RE.match(pid):
        raise ValueError("invalid pack_id")
    return pid


def custom_path(pack_id: str) -> Path:
    return _custom_dir() / f"{assert_pack_id(pack_id)}.pdf"


def pack_asset_path(pack_id: str) -> Path:
    return PACK_ASSETS_DIR / f"{assert_pack_id(pack_id)}.pdf"


def _file_meta(path: Path, *, source: str) -> dict[str, Any]:
    st = path.stat()
    return {
        "exists": True,
        "source": source,
        "path": str(path),
        "filename": path.name,
        "bytes": int(st.st_size),
        "mtime": int(st.st_mtime),
    }


def presentation_meta(pack_id: str | None, settings_path: str | None = None) -> dict[str, Any]:
    """Describe which PDF would be used for a pack right now."""
    try:
        pid = assert_pack_id(pack_id) if pack_id else ""
    except ValueError:
        pid = ""

    if pid:
        custom = custom_path(pid)
        if custom.is_file():
            meta = _file_meta(custom, source="custom")
            meta["pack_id"] = pid
            meta["can_reset"] = True
            return meta
        asset = pack_asset_path(pid)
        if asset.is_file():
            meta = _file_meta(asset, source="pack")
            meta["pack_id"] = pid
            meta["can_reset"] = False
            return meta

    for raw in (settings_path,):
        if not raw:
            continue
        p = Path(str(raw)).expanduser()
        checks = [p, ASSETS_DIR / p, ASSETS_DIR / p.name, PACK_ASSETS_DIR / p.name]
        for c in checks:
            if c.is_file():
                meta = _file_meta(c, source="settings")
                meta["pack_id"] = pid or None
                meta["can_reset"] = False
                return meta

    if DEFAULT_PRESENTATION.is_file():
        meta = _file_meta(DEFAULT_PRESENTATION, source="default")
        meta["pack_id"] = pid or None
        meta["can_reset"] = False
        return meta

    return {
        "exists": False,
        "source": "none",
        "pack_id": pid or None,
        "filename": None,
        "bytes": 0,
        "mtime": None,
        "can_reset": False,
    }


def resolve_presentation(
    *,
    pack_id: str | None = None,
    settings_path: str | None = None,
) -> Path | None:
    meta = presentation_meta(pack_id, settings_path)
    if not meta.get("exists"):
        return None
    path = Path(str(meta["path"]))
    return path if path.is_file() else None


def save_presentation(pack_id: str, raw: bytes, *, original_name: str = "") -> dict[str, Any]:
    if not raw or len(raw) < 100:
        raise ValueError("empty PDF")
    if len(raw) > 30 * 1024 * 1024:
        raise ValueError("PDF too large (max 30MB)")
    # Basic PDF magic
    if not raw.lstrip().startswith(b"%PDF"):
        raise ValueError("file is not a PDF")
    pid = assert_pack_id(pack_id)
    _custom_dir().mkdir(parents=True, exist_ok=True)
    dest = custom_path(pid)
    tmp = dest.with_suffix(".pdf.tmp")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    meta = _file_meta(dest, source="custom")
    meta["pack_id"] = pid
    meta["can_reset"] = True
    meta["original_name"] = (original_name or "").strip() or dest.name
    return meta


def reset_presentation(pack_id: str) -> dict[str, Any]:
    pid = assert_pack_id(pack_id)
    custom = custom_path(pid)
    if custom.is_file():
        custom.unlink()
    return presentation_meta(pid)
