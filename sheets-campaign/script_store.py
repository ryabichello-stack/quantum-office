"""Editable campaign greeting/script stored in DATA_DIR (overrides script.py defaults)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import script as defaults

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-sheets-campaign/data"))
SCRIPT_FILE = DATA_DIR / "campaign_script.json"


def _default_doc() -> dict[str, Any]:
    return {
        "greeting": defaults.GREETING,
        "script": defaults.SCRIPT,
        "tools": list(defaults.CAMPAIGN_TOOLS),
        "source": "builtin",
    }


def load_script() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SCRIPT_FILE.is_file():
        try:
            doc = json.loads(SCRIPT_FILE.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and (doc.get("script") or doc.get("greeting")):
                out = _default_doc()
                if doc.get("greeting") is not None:
                    out["greeting"] = str(doc.get("greeting") or "")
                if doc.get("script") is not None:
                    out["script"] = str(doc.get("script") or "")
                if isinstance(doc.get("tools"), list) and doc["tools"]:
                    out["tools"] = [str(t).strip() for t in doc["tools"] if str(t).strip()]
                out["source"] = "file"
                out["path"] = str(SCRIPT_FILE)
                return out
        except Exception:
            pass
    out = _default_doc()
    out["path"] = str(SCRIPT_FILE)
    return out


def save_script(
    *,
    greeting: str | None = None,
    script: str | None = None,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current = load_script()
    if greeting is not None:
        current["greeting"] = greeting
    if script is not None:
        current["script"] = script
    if tools is not None:
        current["tools"] = [str(t).strip() for t in tools if str(t).strip()] or list(
            defaults.CAMPAIGN_TOOLS
        )
    current["source"] = "file"
    current["path"] = str(SCRIPT_FILE)
    to_write = {
        "greeting": current["greeting"],
        "script": current["script"],
        "tools": current["tools"],
    }
    SCRIPT_FILE.write_text(
        json.dumps(to_write, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return current


def reset_script() -> dict[str, Any]:
    if SCRIPT_FILE.is_file():
        SCRIPT_FILE.unlink()
    return load_script()
