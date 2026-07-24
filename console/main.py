"""Quantum Labs control console — ops UI for AVA telephony stack."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("quantum-console")

CONSOLE_TOKEN = os.getenv("CONSOLE_TOKEN", "").strip()
CONSOLE_USER = os.getenv("CONSOLE_USER", "admin").strip() or "admin"
CONSOLE_PASSWORD = os.getenv("CONSOLE_PASSWORD", "").strip()
# If password empty, fall back to CONSOLE_TOKEN as password (migration).
if not CONSOLE_PASSWORD and CONSOLE_TOKEN:
    CONSOLE_PASSWORD = CONSOLE_TOKEN
CONSOLE_SESSION_SECRET = (
    os.getenv("CONSOLE_SESSION_SECRET", "").strip()
    or CONSOLE_TOKEN
    or "quantum-console-dev-secret"
)
CONSOLE_SESSION_TTL_SEC = int(os.getenv("CONSOLE_SESSION_TTL_SEC", str(7 * 24 * 3600)))
SESSION_COOKIE = "qc_session"
AVA_ROOT = Path(os.getenv("AVA_ROOT", "/root/ava"))
AVA_ENV_PATH = Path(os.getenv("AVA_ENV_PATH", str(AVA_ROOT / ".env")))
AVA_CONFIG_PATH = Path(os.getenv("AVA_CONFIG_PATH", str(AVA_ROOT / "config/ai-agent.local.yaml")))
KNOWLEDGE_PATH = Path(os.getenv("KNOWLEDGE_PATH", str(AVA_ROOT / "config/knowledge/quantum_labs.md")))
CALL_HISTORY_DB = Path(os.getenv("CALL_HISTORY_DB", str(AVA_ROOT / "data/call_history.db")))
MAILER_ENV_PATH = Path(os.getenv("MAILER_ENV_PATH", "/opt/ava-mailer/.env"))
BACKUP_SCRIPT = Path(os.getenv("BACKUP_SCRIPT", str(AVA_ROOT / "scripts/backup_quantum_labs.sh")))

MAILER_HEALTH_URL = os.getenv("MAILER_HEALTH_URL", "http://127.0.0.1:8000/health")
ENGINE_HEALTH_URL = os.getenv("ENGINE_HEALTH_URL", "http://127.0.0.1:15000/health")
TEXT_BOT_HEALTH_URL = os.getenv("TEXT_BOT_HEALTH_URL", "http://127.0.0.1:8011/health")
OUTREACH_HEALTH_URL = os.getenv("OUTREACH_HEALTH_URL", "http://127.0.0.1:8012/health")
OUTREACH_BASE = os.getenv("OUTREACH_BASE", "http://127.0.0.1:8012").rstrip("/")
OUTREACH_UI_TOKEN = os.getenv("OUTREACH_UI_TOKEN", "").strip()
OUTREACH_ENV_PATH = Path(os.getenv("OUTREACH_ENV_PATH", "/opt/ava-outreach/.env"))
CAMPAIGN_BASE = os.getenv("CAMPAIGN_BASE", "http://127.0.0.1:8018").rstrip("/")
CAMPAIGN_TOKEN = os.getenv(
    "CAMPAIGN_TOKEN",
    os.getenv("WEBHOOK_TOKEN", ""),
).strip()
CAMPAIGN_HEALTH_URL = os.getenv("CAMPAIGN_HEALTH_URL", f"{CAMPAIGN_BASE}/health")

OUTBOUND_ENABLED = os.getenv("OUTBOUND_ENABLED", "true").lower() in {"1", "true", "yes"}
OUTBOUND_DIAL_CONTEXT = os.getenv("OUTBOUND_DIAL_CONTEXT", "from-internal")
OUTBOUND_CALLER_ID_NUM = os.getenv("OUTBOUND_CALLER_ID_NUM", "79699665899")
OUTBOUND_CALLER_ID_NAME = os.getenv("OUTBOUND_CALLER_ID_NAME", "Quantum Labs")
OUTBOUND_STASIS_APP = os.getenv("OUTBOUND_STASIS_APP", "asterisk-ai-voice-agent")
OUTBOUND_AI_CONTEXT = os.getenv("OUTBOUND_AI_CONTEXT", "outbound")
# Dedicated Realtime provider block — must NOT share settings with inbound `openai_realtime`.
OUTBOUND_AI_PROVIDER = os.getenv("OUTBOUND_AI_PROVIDER", "openai_realtime_outbound")
INBOUND_AI_PROVIDER = os.getenv("INBOUND_AI_PROVIDER", "openai_realtime")
KNOWLEDGE_RELOAD_URL = os.getenv("KNOWLEDGE_RELOAD_URL", "http://127.0.0.1:8017/api/knowledge/reload")
ALLOWED_AI_CONTEXTS = ("default", "outbound")
CONTEXT_PROVIDER_MAP = {
    "default": INBOUND_AI_PROVIDER,
    "outbound": OUTBOUND_AI_PROVIDER,
}

# Mango VPBX API callback (preferred outbound while SIP PSTN 183→403 on Beget)
MANGO_VPBX_API_KEY = os.getenv("MANGO_VPBX_API_KEY", "").strip()
MANGO_VPBX_API_SALT = os.getenv("MANGO_VPBX_API_SALT", "").strip()
MANGO_API_ENV_PATH = Path(
    os.getenv("MANGO_API_ENV_PATH", "/root/mango-ip-ab-investigation/mango-api.env")
)
MANGO_CALLBACK_EXTENSION = os.getenv("MANGO_CALLBACK_EXTENSION", "12").strip() or "12"
MANGO_VPBX_API_BASE = os.getenv(
    "MANGO_VPBX_API_BASE", "https://app.mango-office.ru/vpbx"
).rstrip("/")

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Quantum Labs Console", version="0.1.0")
if STATIC_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")


def _load_outreach_ui_token() -> str:
    """Resolve OUTREACH_UI_TOKEN for server-side proxy (never expose to browser)."""
    if OUTREACH_UI_TOKEN:
        return OUTREACH_UI_TOKEN
    try:
        if OUTREACH_ENV_PATH.is_file():
            for line in OUTREACH_ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("OUTREACH_UI_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as exc:
        logger.warning("read OUTREACH_UI_TOKEN failed: %s", exc)
    return ""


# ---------------------------------------------------------------------------
# Auth / helpers
# ---------------------------------------------------------------------------

_PUBLIC_API_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
}


def _session_secret_bytes() -> bytes:
    return CONSOLE_SESSION_SECRET.encode("utf-8")


def _sign_session(username: str) -> str:
    exp = int(time.time()) + max(3600, CONSOLE_SESSION_TTL_SEC)
    payload = f"{username}:{exp}"
    sig = hmac.new(_session_secret_bytes(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}:{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _verify_session(cookie: str | None) -> str | None:
    if not cookie:
        return None
    try:
        raw = base64.urlsafe_b64decode(cookie.encode("ascii")).decode("utf-8")
        user, exp_s, sig = raw.rsplit(":", 2)
        payload = f"{user}:{exp_s}"
        expect = hmac.new(
            _session_secret_bytes(), payload.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return None
        if int(exp_s) < int(time.time()):
            return None
        if user != CONSOLE_USER:
            return None
        return user
    except Exception:
        return None


def _password_ok(password: str) -> bool:
    if not CONSOLE_PASSWORD:
        return False
    return hmac.compare_digest(password, CONSOLE_PASSWORD)


def _extract_token(
    request: Request | None = None,
    x_console_token: str | None = None,
    authorization: str | None = None,
) -> str:
    """Accept X-Console-Token or Authorization: Bearer <token>."""
    # Back-compat: some callers still do _require_token(token_str)
    if isinstance(request, str):
        x_console_token = request
        request = None
    if x_console_token and x_console_token.strip():
        return x_console_token.strip()
    if authorization and authorization.strip():
        raw = authorization.strip()
        if raw.lower().startswith("bearer "):
            return raw[7:].strip()
        return raw
    if request is not None and hasattr(request, "headers"):
        h = request.headers
        xt = h.get("x-console-token") or h.get("X-Console-Token")
        if xt and xt.strip():
            return xt.strip()
        auth = h.get("authorization") or h.get("Authorization")
        if auth and auth.strip():
            raw = auth.strip()
            if raw.lower().startswith("bearer "):
                return raw[7:].strip()
            return raw
    return ""


def _request_authenticated(request: Request) -> bool:
    """True if valid API token or login session cookie."""
    tok = _extract_token(request)
    if CONSOLE_TOKEN and tok and hmac.compare_digest(tok, CONSOLE_TOKEN):
        return True
    user = _verify_session(request.cookies.get(SESSION_COOKIE))
    return bool(user)


def _require_token(
    request: Request | None = None,
    x_console_token: str | None = None,
    authorization: str | None = None,
) -> None:
    """Prefer middleware for /api/*. Endpoint calls may only see X-Console-Token Header.

    If the client sent Authorization: Bearer, the Header param is empty — do not
    reject; middleware already validated the request.
    """
    # Back-compat: _require_token(token_str) from older endpoint bodies
    if isinstance(request, str):
        x_console_token = request
        request = None
    if not CONSOLE_TOKEN and not CONSOLE_PASSWORD:
        raise HTTPException(503, "CONSOLE auth is not configured on server")
    got = _extract_token(request, x_console_token, authorization)
    if got and CONSOLE_TOKEN and not hmac.compare_digest(got, CONSOLE_TOKEN):
        raise HTTPException(
            401,
            "invalid or missing token (use header X-Console-Token or Authorization: Bearer …)",
        )


@app.middleware("http")
async def _api_auth_middleware(request: Request, call_next):
    path = request.url.path or ""
    # Strip public prefix if proxied oddly
    if path.startswith("/_quantum_console/"):
        path = path[len("/_quantum_console") :] or "/"
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
        if not CONSOLE_TOKEN and not CONSOLE_PASSWORD:
            return JSONResponse(
                status_code=503,
                content={"detail": "Console auth is not configured on server"},
            )
        if not _request_authenticated(request):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "unauthorized — login or pass X-Console-Token / Bearer token"
                },
            )
    return await call_next(request)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1, max_length=200)


@app.post("/api/auth/login")
def api_auth_login(body: LoginRequest):
    user = (body.username or "").strip()
    password = body.password or ""
    if user != CONSOLE_USER or not _password_ok(password):
        raise HTTPException(401, "Неверный логин или пароль")
    token = _sign_session(user)
    resp = JSONResponse(
        {
            "ok": True,
            "user": user,
            "message": "Вход выполнен",
        }
    )
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=CONSOLE_SESSION_TTL_SEC,
        path="/",
    )
    return resp


@app.post("/api/auth/logout")
def api_auth_logout():
    resp = JSONResponse({"ok": True, "message": "Выход выполнен"})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def api_auth_me(request: Request):
    user = _verify_session(request.cookies.get(SESSION_COOKIE))
    tok = _extract_token(request)
    token_ok = bool(CONSOLE_TOKEN and tok and hmac.compare_digest(tok, CONSOLE_TOKEN))
    if user:
        return {"ok": True, "authenticated": True, "user": user, "via": "session"}
    if token_ok:
        return {"ok": True, "authenticated": True, "user": CONSOLE_USER, "via": "token"}
    return {"ok": True, "authenticated": False, "user": None}


def _restart_ai_engine() -> dict[str, Any]:
    """Reload scripts into running engine."""
    rc, out = _run(["docker", "restart", "ai_engine"], timeout=120)
    if rc != 0:
        rc2, out2 = _run(
            [
                "docker",
                "compose",
                "-f",
                str(AVA_ROOT / "docker-compose.yml"),
                "up",
                "-d",
                "--no-build",
                "ai_engine",
            ],
            timeout=120,
        )
        return {
            "ok": rc2 == 0,
            "method": "compose_up",
            "exit_code": rc2,
            "output": (out + "\n" + out2)[-2000:],
        }
    healthy = False
    for _ in range(20):
        time.sleep(1)
        if _http_ok(ENGINE_HEALTH_URL, timeout=2.0):
            healthy = True
            break
    return {
        "ok": rc == 0 and healthy,
        "method": "docker_restart",
        "exit_code": rc,
        "healthy": healthy,
        "output": out[-1000:],
    }


def _read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _mango_api_creds() -> tuple[str, str]:
    key = MANGO_VPBX_API_KEY
    salt = MANGO_VPBX_API_SALT
    if (not key or not salt) and MANGO_API_ENV_PATH.is_file():
        env = _read_env_file(MANGO_API_ENV_PATH)
        key = key or env.get("MANGO_VPBX_API_KEY", "") or env.get("vpbx_api_key", "")
        salt = salt or env.get("MANGO_VPBX_API_SALT", "") or env.get("vpbx_api_salt", "")
    return key.strip(), salt.strip()


def _mango_sign(api_key: str, json_str: str, salt: str) -> str:
    return hashlib.sha256((api_key + json_str + salt).encode("utf-8")).hexdigest()


def _mango_api_post(path: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any] | str]:
    key, salt = _mango_api_creds()
    if not key or not salt:
        raise HTTPException(503, "Mango API key/salt not configured")
    json_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    body = urllib.parse.urlencode(
        {
            "vpbx_api_key": key,
            "sign": _mango_sign(key, json_str, salt),
            "json": json_str,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{MANGO_VPBX_API_BASE}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        try:
            return e.code, json.loads(detail)
        except json.JSONDecodeError:
            return e.code, detail


def _http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False


def _run(cmd: list[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = ((p.stdout or "") + (p.stderr or "")).strip()
        return p.returncode, out
    except Exception as e:
        return 1, str(e)


def _normalize_phone(raw: str) -> str:
    s = (raw or "").strip()
    digits = re.sub(r"[^\d+]", "", s)
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if not digits.isdigit() or len(digits) < 10:
        raise HTTPException(400, "phone must be 10+ digits (E.164 without + preferred, e.g. 79001234567)")
    return digits


def _load_yaml() -> dict[str, Any]:
    if not AVA_CONFIG_PATH.is_file():
        raise HTTPException(404, f"config not found: {AVA_CONFIG_PATH}")
    data = yaml.safe_load(AVA_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise HTTPException(500, "invalid YAML root")
    return data


def _backup_config() -> None:
    bak = AVA_CONFIG_PATH.with_suffix(AVA_CONFIG_PATH.suffix + ".bak.console")
    bak.write_text(AVA_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _replace_simple_key(text: str, key: str, value: str | float, *, within: str | None = None) -> str:
    """Replace `key: ...` scalar line. Optionally limit to a section name occurrence window."""
    body = text
    start = 0
    if within:
        m = re.search(rf"(?m)^{re.escape(within)}:\s*$", body)
        if not m:
            raise HTTPException(400, f"section '{within}' not found in YAML")
        start = m.start()
    chunk = body[start:]
    if isinstance(value, float):
        rep = f"{key}: {value}"
        pat = rf"(?m)^(\s*){re.escape(key)}:\s*[^\n]*$"
        chunk2, n = re.subn(pat, rf"\1{rep}", chunk, count=1)
    else:
        # Always JSON-quote strings to keep YAML safe (Cyrillic, colons, etc.).
        if "\n" in str(value):
            raise HTTPException(400, f"{key}: use dedicated multiline editor path")
        rep_val = json.dumps(str(value), ensure_ascii=False)
        pat = rf"(?m)^(\s*){re.escape(key)}:\s*[^\n]*$"
        chunk2, n = re.subn(pat, rf"\1{key}: {rep_val}", chunk, count=1)
    if n != 1:
        raise HTTPException(400, f"could not update key '{key}'")
    return body[:start] + chunk2


def _replace_folded_prompt(text: str, new_prompt: str) -> str:
    """Replace contexts.default.prompt folded/literal block."""
    # Match `prompt: |` or `prompt: >` or single-line prompt under default context.
    m = re.search(
        r"(?ms)^(?P<indent>    )prompt:\s*(?P<style>[|>][^\n]*)?\n(?P<body>(?:^(?:      |\t).*\n?)+)",
        text,
    )
    if not m:
        # try single-line
        m2 = re.search(r"(?m)^(    prompt:\s*).+$", text)
        if not m2:
            raise HTTPException(400, "contexts.default.prompt block not found")
        return text[: m2.start()] + f"    prompt: {json.dumps(new_prompt, ensure_ascii=False)}" + text[m2.end() :]
    indent = "      "
    body_lines = new_prompt.replace("\r\n", "\n").split("\n")
    body = "".join(indent + (line if line else "") + "\n" for line in body_lines)
    if not body.endswith("\n"):
        body += "\n"
    replacement = f"{m.group('indent')}prompt: |\n{body}"
    return text[: m.start()] + replacement + text[m.end() :]


def _pack_inventory() -> list[dict[str, Any]]:
    """Canonical Quantum pack — what you unpack on a new server."""
    items = [
        ("ava_config", str(AVA_CONFIG_PATH), "Сценарий: greeting, prompt, tools, model/voice"),
        ("knowledge", str(KNOWLEDGE_PATH), "База знаний секретаря"),
        ("asterisk_pjsip", str(AVA_ROOT / "config/asterisk/pjsip.quantum-labs.conf"), "Mango SIP trunk (секреты)"),
        ("asterisk_dialplan", str(AVA_ROOT / "config/asterisk/extensions.quantum-labs.conf"), "In/outbound dialplan"),
        ("ava_env", str(AVA_ENV_PATH), "ARI + OpenAI secrets"),
        ("mailer_env", str(MAILER_ENV_PATH), "SMTP / CalDAV / Telemost / webhook"),
        ("mailer_code", "/opt/ava-mailer/main.py", "Календарь, post-call, knowledge API"),
        ("yandex_tokens", "/opt/ava-mailer/yandex_oauth_tokens.json", "OAuth Телемост"),
        ("call_history", str(CALL_HISTORY_DB), "Транскрипты и outbound state"),
        ("backup_script", str(BACKUP_SCRIPT), "Полный tar-бэкап"),
        ("passport", str(AVA_ROOT / "docs/AVA_QUANTUM_LABS_SYSTEM.md"), "Паспорт системы"),
    ]
    out = []
    for key, path, note in items:
        p = Path(path)
        out.append(
            {
                "key": key,
                "path": path,
                "note": note,
                "exists": p.exists(),
                "size_bytes": p.stat().st_size if p.is_file() else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ScenarioUpdate(BaseModel):
    context: str | None = Field(default="default", description="AVA context: default|outbound")
    greeting: str | None = None
    prompt: str | None = Field(default=None, description="Full conversation script / system prompt")
    model: str | None = None
    voice: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    provider: str | None = None
    tools: list[str] | None = Field(
        default=None,
        description="In-call tools for this profile only (e.g. get_company_knowledge, hangup_call)",
    )
    use_knowledge: bool | None = Field(
        default=None,
        description="If false, remove get_company_knowledge from tools; if true, ensure it is present",
    )
    restart: bool = Field(
        default=True,
        description="Restart ai_engine after save so the new script applies immediately",
    )


class OutboundScriptUpdate(BaseModel):
    """Full outbound conversation script — preferred API for setting the whole context."""

    greeting: str = Field(..., min_length=1, description="First spoken line")
    script: str = Field(
        ...,
        min_length=1,
        description="Full playbook / system prompt for the outbound call (replaces contexts.outbound.prompt)",
    )
    use_knowledge: bool = Field(
        default=True,
        description="If true, bot may call Second Brain for missing facts; if false — only your script",
    )
    tools: list[str] | None = Field(
        default=None,
        description="Optional explicit tools list; overrides use_knowledge defaults",
    )
    model: str | None = None
    voice: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    restart: bool = True


class KnowledgeUpdate(BaseModel):
    text: str
    reload: bool = True


class DialRequest(BaseModel):
    phone: str
    context: str | None = Field(default=None, description="AVA context profile (default|outbound)")
    provider: str | None = None
    caller_id_num: str | None = None
    caller_id_name: str | None = None
    # Per-call conversation context (does NOT rewrite global YAML)
    greeting: str | None = Field(
        default=None,
        description="First spoken line for THIS call only",
    )
    script: str | None = Field(
        default=None,
        description="Full playbook/system prompt for THIS call only (overrides YAML outbound prompt)",
    )
    tools: list[str] | None = Field(
        default=None,
        description=(
            "In-call tools for THIS call only (overrides YAML outbound.tools). "
            "See GET /api/tools for the full catalog. Explicit list wins over use_knowledge."
        ),
    )
    use_knowledge: bool = Field(
        default=False,
        description=(
            "Convenience: ensure get_company_knowledge is in per-call tools and append "
            "Second Brain footer to script. Ignored for tool selection when tools= is set "
            "(still adds KB footer if get_company_knowledge is in the resolved list)."
        ),
    )


class CallbackRequest(BaseModel):
    phone: str
    extension: str | None = None
    line_number: str | None = None
    command_id: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    index_path = STATIC_DIR / "index.html"
    if not index_path.is_file():
        raise HTTPException(404, "UI not installed")
    return FileResponse(index_path)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "quantum-console"}


@app.get("/api/status")
def api_status(x_console_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_console_token)
    rc_reg, reg_out = _run(["asterisk", "-rx", "pjsip show registrations"], timeout=10)
    mango_registered = "Registered" in reg_out
    rc_dp, dp_out = _run(["asterisk", "-rx", "dialplan show from-internal"], timeout=10)
    outbound_dialplan = "from-internal" in dp_out and (
        "mango-employee" in dp_out or "mango-endpoint" in dp_out or "mango-trunk" in dp_out
    )
    rc_amd, amd_out = _run(["asterisk", "-rx", "dialplan show aava-outbound-amd"], timeout=10)
    amd_dialplan = "aava-outbound-amd" in amd_out and "AMD(" in amd_out

    units = {}
    for u in (
        "asterisk",
        "ava-mailer",
        "quantum-ava-docker",
        "ava-text-bot",
        "ava-outreach",
        "quantum-console",
        "ava-sheets-campaign",
    ):
        rc, out = _run(["systemctl", "is-active", u], timeout=5)
        units[u] = out.strip() or ("inactive" if rc else "unknown")

    mango_key, mango_salt = _mango_api_creds()
    mango_api_ok = bool(mango_key and mango_salt)
    host_raw = os.uname().nodename
    # Friendly labels for UI (avoid exposing random VPS hostnames as brand)
    health = {
        "mailer": _http_ok(MAILER_HEALTH_URL),
        "ai_engine": _http_ok(ENGINE_HEALTH_URL),
        "text_bot": _http_ok(TEXT_BOT_HEALTH_URL),
        "outreach": _http_ok(OUTREACH_HEALTH_URL),
        "sheets_campaign": _http_ok(CAMPAIGN_HEALTH_URL),
    }
    services = [
        {
            "id": "mailer",
            "label": _SERVICE_LABELS["mailer"],
            "ok": health["mailer"],
            "hint": "порт 8000 · письма, welcome, knowledge proxy",
        },
        {
            "id": "ai_engine",
            "label": _SERVICE_LABELS["ai_engine"],
            "ok": health["ai_engine"],
            "hint": "Realtime голос · docker ai_engine",
        },
        {
            "id": "text_bot",
            "label": _SERVICE_LABELS["text_bot"],
            "ok": health["text_bot"],
            "hint": "порт 8011 · секретарь в Telegram",
        },
        {
            "id": "outreach",
            "label": _SERVICE_LABELS["outreach"],
            "ok": health["outreach"],
            "hint": "порт 8012 · Bitrix",
        },
        {
            "id": "sheets_campaign",
            "label": _SERVICE_LABELS["sheets_campaign"],
            "ok": health["sheets_campaign"],
            "hint": "порт 8018 · обзвон из Google Sheet",
        },
        {
            "id": "mango_sip",
            "label": "Mango SIP",
            "ok": mango_registered,
            "hint": "регистрация транка на АТС",
        },
        {
            "id": "outbound_dialplan",
            "label": "Исходящий dialplan",
            "ok": outbound_dialplan,
            "hint": "контекст from-internal",
        },
        {
            "id": "amd_dialplan",
            "label": "AMD (автоответчик)",
            "ok": amd_dialplan,
            "hint": "детектор автоответчика",
        },
    ]
    units_ui = [
        {
            "id": k,
            "label": _UNIT_LABELS.get(k, k),
            "state": v,
            "ok": v == "active",
        }
        for k, v in units.items()
    ]
    # Quick tool summary for status → drill into scenario
    try:
        inbound_tools = list((_load_yaml().get("contexts") or {}).get("default", {}).get("tools") or [])
        outbound_tools = list((_load_yaml().get("contexts") or {}).get("outbound", {}).get("tools") or [])
    except Exception:
        inbound_tools, outbound_tools = [], []
    catalog = {t["name"]: t for t in _tool_catalog()["tools"]}

    def _tool_chips(names: list[str]) -> list[dict[str, str]]:
        out = []
        for n in names:
            meta = catalog.get(n) or _enrich_tool({"name": n, "group": "other", "label": n})
            out.append(
                {
                    "name": n,
                    "label": meta.get("label") or n,
                    "description": meta.get("description") or "",
                    "group_label": meta.get("group_label") or "",
                }
            )
        return out

    return {
        "host": host_raw,
        "host_label": "Quantum Labs · телефония",
        "host_note": f"системное имя хоста: {host_raw}",
        "health": health,
        "services": services,
        "units": units,
        "units_ui": units_ui,
        "mango_registered": mango_registered,
        "registration_raw": "\n".join(reg_out.splitlines()[:12]),
        "outbound": {
            "enabled_flag": OUTBOUND_ENABLED,
            "dialplan_from_internal": outbound_dialplan,
            "dialplan_amd": amd_dialplan,
            "dial_context": OUTBOUND_DIAL_CONTEXT,
            "mango_api_configured": mango_api_ok,
            "mango_callback_extension": MANGO_CALLBACK_EXTENSION,
            "preferred": "mango_api_callback" if mango_api_ok else "sip_pjsip",
        },
        "profiles": {
            "inbound": {
                "context": "default",
                "label": "Входящие",
                "tools": _tool_chips(inbound_tools),
            },
            "outbound": {
                "context": "outbound",
                "label": "Исходящие",
                "tools": _tool_chips(outbound_tools),
            },
        },
        "pack": _pack_inventory(),
        "paths": {
            "ava_config": str(AVA_CONFIG_PATH),
            "knowledge": str(KNOWLEDGE_PATH),
            "call_history_db": str(CALL_HISTORY_DB),
        },
    }


def _normalize_ai_context(name: str | None) -> str:
    ctx = (name or "default").strip() or "default"
    if ctx not in ALLOWED_AI_CONTEXTS:
        raise HTTPException(400, f"context must be one of {ALLOWED_AI_CONTEXTS}")
    return ctx


def _dedicated_provider_name(context: str) -> str:
    """Provider block owned by this call profile (inbound ≠ outbound)."""
    return CONTEXT_PROVIDER_MAP.get(context) or INBOUND_AI_PROVIDER


def _ensure_dedicated_provider(data: dict[str, Any], context: str) -> str:
    """Attach a private providers.* block to the context; never share with the other profile."""
    import copy

    wanted = _dedicated_provider_name(context)
    providers = data.setdefault("providers", {})
    contexts = data.setdefault("contexts", {})
    ctx = contexts.setdefault(context, {})
    other = "outbound" if context == "default" else "default"
    other_wanted = _dedicated_provider_name(other)

    # Seed missing dedicated provider from the other side's template once, then keep separate.
    if wanted not in providers or not isinstance(providers.get(wanted), dict):
        template = None
        for cand in (ctx.get("provider"), other_wanted, "openai_realtime", data.get("default_provider")):
            if cand and isinstance(providers.get(cand), dict):
                template = providers[cand]
                break
        providers[wanted] = copy.deepcopy(template or {})
    ctx["provider"] = wanted

    # Inbound keeps global default_provider; outbound must never steal it.
    if context == "default":
        data["default_provider"] = wanted
    return wanted


def _scenario_payload(context: str) -> dict[str, Any]:
    data = _load_yaml()
    contexts = data.get("contexts") or {}
    ctx = contexts.get(context) or {}
    if not ctx and context != "default":
        raise HTTPException(404, f"context '{context}' not found in YAML")
    prov_name = ctx.get("provider") or _dedicated_provider_name(context)
    # Prefer dedicated name even if YAML still points at a shared legacy provider.
    if context in CONTEXT_PROVIDER_MAP and prov_name == CONTEXT_PROVIDER_MAP.get(
        "outbound" if context == "default" else "default"
    ):
        prov_name = _dedicated_provider_name(context)
    prov = (data.get("providers") or {}).get(prov_name) or {}
    label = "входящие" if context == "default" else "исходящие"
    return {
        "context": context,
        "profile_label": label,
        "isolated": True,
        "available_contexts": sorted(contexts.keys()),
        "greeting": ctx.get("greeting") or "",
        "prompt": ctx.get("prompt") or "",
        "provider": prov_name,
        "tools": ctx.get("tools") or [],
        "post_call_tools": ctx.get("post_call_tools") or [],
        "model": prov.get("model"),
        "voice": prov.get("voice"),
        "temperature": prov.get("temperature"),
        "config_path": str(AVA_CONFIG_PATH),
        "knowledge_mode": "second_brain via get_company_knowledge → ava-knowledge",
        "transcripts": "call_history.db conversation_history (auto)",
        "note": (
            "Профили изолированы: правки default не меняют outbound и наоборот "
            "(отдельные greeting/prompt/provider)."
        ),
    }


@app.get("/api/scenario")
def api_scenario_get(
    context: str = "default",
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    return _scenario_payload(_normalize_ai_context(context))


@app.put("/api/scenario")
def api_scenario_put(
    body: ScenarioUpdate,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Update ONE call profile only. Inbound (`default`) and outbound stay isolated."""
    _require_token(x_console_token)
    ctx_name = _normalize_ai_context(body.context)
    _backup_config()
    data = _load_yaml()
    contexts = data.setdefault("contexts", {})
    other_name = "outbound" if ctx_name == "default" else "default"
    # Snapshot the other profile so we can refuse writes that would mutate it.
    other_before = json.dumps(contexts.get(other_name) or {}, ensure_ascii=False, sort_keys=True)
    inbound_prov_before = json.dumps(
        (data.get("providers") or {}).get(INBOUND_AI_PROVIDER) or {},
        ensure_ascii=False,
        sort_keys=True,
    )
    outbound_prov_before = json.dumps(
        (data.get("providers") or {}).get(OUTBOUND_AI_PROVIDER) or {},
        ensure_ascii=False,
        sort_keys=True,
    )

    if ctx_name not in contexts:
        import copy

        # Bootstrap structure only; do not copy inbound playbook into outbound by default.
        seed = {"tools": ["get_company_knowledge", "hangup_call"], "provider": _dedicated_provider_name(ctx_name)}
        if ctx_name == "outbound":
            # Neutral shell only — never seed Quantum Labs / Garik playbook here.
            # Outbound results live in Console «Звонки» (transcript table), NOT lead email.
            seed["tools"] = ["hangup_call"]
            seed["post_call_tools"] = []
            seed["greeting"] = ""
            seed["prompt"] = (
                "Ты — голосовой ассистент на исходящем звонке. "
                "Нет заранее заданного продукта или компании. "
                "Действуй только по per-call сценарию из dial API. "
                "Без сценария — коротко представься и спроси, чем помочь. "
                "Не питчи Quantum Labs / выплаты / СБП и не предлагай встречу сам."
            )
        else:
            seed = copy.deepcopy(contexts.get("outbound") or seed)
        contexts[ctx_name] = seed

    ctx = contexts[ctx_name]
    if body.greeting is not None:
        ctx["greeting"] = body.greeting
    if body.prompt is not None:
        ctx["prompt"] = body.prompt

    # Always pin this context to its dedicated provider; ignore cross-profile provider names.
    prov_name = _ensure_dedicated_provider(data, ctx_name)
    if body.provider is not None:
        requested = body.provider.strip()
        # Allow only the dedicated name for this profile (or explicit match).
        if requested and requested not in {prov_name, _dedicated_provider_name(ctx_name)}:
            logger.warning(
                "ignoring provider=%s for context=%s; forcing dedicated %s",
                requested,
                ctx_name,
                prov_name,
            )

    prov = data.setdefault("providers", {}).setdefault(prov_name, {})
    if body.model is not None:
        prov["model"] = body.model
    if body.voice is not None:
        prov["voice"] = body.voice
    if body.temperature is not None:
        prov["temperature"] = float(body.temperature)

    # Tools: explicit list wins; else use_knowledge toggles Second Brain tool.
    if body.tools is not None:
        ctx["tools"] = [str(t).strip() for t in body.tools if str(t).strip()]
    elif body.use_knowledge is not None:
        tools = list(ctx.get("tools") or [])
        if body.use_knowledge:
            if "get_company_knowledge" not in tools:
                tools.append("get_company_knowledge")
            if "hangup_call" not in tools:
                tools.append("hangup_call")
        else:
            tools = [t for t in tools if t != "get_company_knowledge"]
            if "hangup_call" not in tools:
                tools.append("hangup_call")
        ctx["tools"] = tools
    elif ctx_name == "outbound" and not ctx.get("tools"):
        ctx["tools"] = ["hangup_call"]

    if ctx_name == "outbound":
        # Explicit empty list: do NOT re-seed mailru_post_call (inbound-only lead emails).
        ctx["post_call_tools"] = []

    other_after = json.dumps(contexts.get(other_name) or {}, ensure_ascii=False, sort_keys=True)
    if other_after != other_before:
        raise HTTPException(500, f"refusing to write: other profile '{other_name}' would change")
    if ctx_name == "outbound":
        inbound_prov_after = json.dumps(
            (data.get("providers") or {}).get(INBOUND_AI_PROVIDER) or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        if inbound_prov_after != inbound_prov_before:
            raise HTTPException(500, "refusing to write: inbound provider settings would change")
    else:
        outbound_prov_after = json.dumps(
            (data.get("providers") or {}).get(OUTBOUND_AI_PROVIDER) or {},
            ensure_ascii=False,
            sort_keys=True,
        )
        if outbound_prov_after != outbound_prov_before:
            raise HTTPException(500, "refusing to write: outbound provider settings would change")

    dumped = yaml.safe_dump(
        data,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    )
    parsed = yaml.safe_load(dumped)
    if not isinstance(parsed, dict) or "contexts" not in parsed:
        raise HTTPException(500, "refusing to write: YAML validation failed after edit")
    AVA_CONFIG_PATH.write_text(dumped, encoding="utf-8")
    logger.info("scenario updated context=%s provider=%s path=%s", ctx_name, prov_name, AVA_CONFIG_PATH)
    restart_info: dict[str, Any] | None = None
    if body.restart:
        restart_info = _restart_ai_engine()
    return {
        "ok": True,
        "isolated_from": other_name,
        "applied": bool(restart_info and restart_info.get("ok")) if body.restart else False,
        "engine_restart": restart_info,
        "note": (
            f"Сохранён только профиль '{ctx_name}' (provider={prov_name}). "
            + (
                "Engine перезапущен — новый скрипт активен."
                if restart_info and restart_info.get("ok")
                else (
                    "Engine restart failed — вызови POST /api/actions/restart-engine."
                    if body.restart
                    else "Restart ai_engine чтобы применить (или restart=true)."
                )
            )
        ),
        **_scenario_payload(ctx_name),
    }


KNOWLEDGE_SCRIPT_FOOTER = (
    "\n\nИСТОЧНИК ФАКТОВ — SECOND BRAIN:\n"
    "- Если в скрипте выше не хватает конкретного факта (цифры, тарифы, контакты, продукт) — "
    "молча вызови tool get_company_knowledge с коротким topic.\n"
    "- Не уходи в чужие темы из базы знаний, если они не нужны для ЭТОГО скрипта.\n"
    "- После tool отвечай по сути скрипта, без служебных фраз «сейчас проверю».\n"
)

HANGUP_GUARD_FOOTER = (
    "\n\nКРИТИЧНО — НЕ РВИ ТРУБКУ РАНО:\n"
    "- ЗАПРЕЩЕНО вызывать hangup_call в первые 60 секунд и на первой реплике собеседника.\n"
    "- Обрывки ASR («авто», «сообщения», шум) НЕ считай автоответчиком — переспроси «Алло, меня слышно?».\n"
    "- hangup_call только при ясном отказе человека ИЛИ после короткого farewell на ЯВНЫЙ автоответчик "
    "(«оставьте сообщение после сигнала»), не раньше.\n"
)

# Built-in AVA in-call tools (engine registry). HTTP tools come from YAML in_call_tools.
_BUILTIN_IN_CALL_TOOLS: list[dict[str, str]] = [
    {"name": "hangup_call", "group": "telephony", "label": "Завершить звонок"},
    {"name": "leave_voicemail", "group": "telephony", "label": "Оставить голосовое"},
    {"name": "blind_transfer", "group": "telephony", "label": "Слепой перевод"},
    {"name": "attended_transfer", "group": "telephony", "label": "Сопровождаемый перевод"},
    {"name": "cancel_transfer", "group": "telephony", "label": "Отменить перевод"},
    {"name": "live_agent_transfer", "group": "telephony", "label": "Перевод на оператора"},
    {"name": "transfer_call", "group": "telephony", "label": "Перевод звонка"},
    {"name": "transfer_to_queue", "group": "telephony", "label": "Перевод в очередь"},
    {"name": "check_extension_status", "group": "telephony", "label": "Статус добавочного"},
    {"name": "google_calendar", "group": "business", "label": "Google Calendar (встроенный)"},
    {"name": "request_transcript", "group": "business", "label": "Запросить транскрипт"},
    {"name": "send_email_summary", "group": "business", "label": "Email-сводка звонка"},
]

# Human labels / descriptions for Console UI (builtins + HTTP Quantum tools).
_TOOL_META: dict[str, dict[str, str]] = {
    "hangup_call": {
        "label": "Завершить звонок",
        "description": "Положить трубку. Не вызывать в первые секунды и на обрывках ASR.",
        "group": "telephony",
    },
    "leave_voicemail": {
        "label": "Оставить голосовое",
        "description": "Запись сообщения на автоответчик собеседника.",
        "group": "telephony",
    },
    "blind_transfer": {
        "label": "Слепой перевод",
        "description": "Перевести звонок без предварительного разговора с целью.",
        "group": "telephony",
    },
    "attended_transfer": {
        "label": "Сопровождаемый перевод",
        "description": "Перевод с удержанием и представлением оператору.",
        "group": "telephony",
    },
    "cancel_transfer": {
        "label": "Отменить перевод",
        "description": "Отмена незавершённого перевода.",
        "group": "telephony",
    },
    "live_agent_transfer": {
        "label": "Перевод на оператора",
        "description": "Соединить с живым сотрудником.",
        "group": "telephony",
    },
    "transfer_call": {
        "label": "Перевод звонка",
        "description": "Унифицированный перевод (engine).",
        "group": "telephony",
    },
    "transfer_to_queue": {
        "label": "Перевод в очередь",
        "description": "Поставить звонок в очередь ожидания.",
        "group": "telephony",
    },
    "check_extension_status": {
        "label": "Статус добавочного",
        "description": "Проверить, доступен ли внутренний номер.",
        "group": "telephony",
    },
    "google_calendar": {
        "label": "Google Calendar (встроенный)",
        "description": "Встроенный календарь engine — у Quantum Labs обычно не используется.",
        "group": "business",
    },
    "request_transcript": {
        "label": "Запросить транскрипт",
        "description": "Запросить текст разговора во время звонка.",
        "group": "business",
    },
    "send_email_summary": {
        "label": "Email-сводка",
        "description": "Отправить краткое резюме звонка на почту.",
        "group": "business",
    },
    "get_company_knowledge": {
        "label": "Second Brain — база знаний",
        "description": "Факты о компании через knowledge (:8017 / mailer proxy).",
        "group": "business",
    },
    "check_calendar": {
        "label": "Проверить календарь",
        "description": "Свободные слоты через calendar-сервис (:8014).",
        "group": "business",
    },
    "create_calendar_event": {
        "label": "Создать встречу",
        "description": "Запись в календарь через calendar-сервис (:8014).",
        "group": "business",
    },
    "create_conference": {
        "label": "Создать конференцию",
        "description": "Ссылка Яндекс Телемост через conference (:8016).",
        "group": "business",
    },
    "send_welcome_email": {
        "label": "Welcome-письмо",
        "description": "Презентация / welcome через mailer (:8000).",
        "group": "business",
    },
    "send_email": {
        "label": "Отправить email",
        "description": "Произвольное письмо (to, subject, body) через mailer.",
        "group": "business",
    },
    "ai_identity": {
        "label": "Идентичность AI",
        "description": "Служебный tool профиля (обычно не включать вручную).",
        "group": "http",
    },
    "sample_n8n_in_call_tool": {
        "label": "Пример n8n (образец)",
        "description": "Демо-tool из YAML AVA — не для продакшена Quantum.",
        "group": "http",
    },
    "mailru_post_call": {
        "label": "Post-call → Mail.ru / лид",
        "description": "После звонка: письмо «Новый лид» (только входящие).",
        "group": "post_call",
    },
}

_TOOL_META_SKIP_NAMES = {
    "enabled",
    "extensions",
    "transfer",
    "default_action_timeout",
    "sample_gohighlevel_pre_call_lookup",
    "demo_post_call_webhook",
    "sample_discord_post_call_webhook",
}

_GROUP_LABELS = {
    "telephony": "Телефония",
    "business": "Бизнес",
    "http": "HTTP / интеграции",
    "post_call": "После звонка",
    "other": "Прочее",
}

_SERVICE_LABELS = {
    "mailer": "Почта и welcome",
    "ai_engine": "Голосовой AI (AVA)",
    "text_bot": "Telegram-бот",
    "outreach": "Bitrix / outreach",
    "sheets_campaign": "Кампания Sheets",
    "mango SIP": "Регистрация Mango SIP",
    "outbound DP": "Dialplan исходящих",
    "AMD DP": "Dialplan AMD",
}

_UNIT_LABELS = {
    "asterisk": "Asterisk",
    "ava-mailer": "Почта (mailer)",
    "quantum-ava-docker": "Docker AVA / AI engine",
    "ava-text-bot": "Telegram-бот",
    "ava-outreach": "Outreach Bitrix",
    "quantum-console": "Эта консоль",
    "ava-sheets-campaign": "Кампания Sheets",
}


def _enrich_tool(t: dict[str, Any]) -> dict[str, Any]:
    name = str(t.get("name") or "")
    meta = _TOOL_META.get(name) or {}
    out = dict(t)
    if meta.get("label"):
        out["label"] = meta["label"]
    elif not out.get("label") or out.get("label") == name:
        out["label"] = name.replace("_", " ")
    if meta.get("description"):
        out["description"] = meta["description"]
    else:
        out.setdefault("description", "")
    if meta.get("group"):
        out["group"] = meta["group"]
    out["group_label"] = _GROUP_LABELS.get(str(out.get("group") or "other"), str(out.get("group") or ""))
    return out


def _tool_catalog() -> dict[str, Any]:
    """Full in-call tool catalog: builtins + YAML HTTP tools (base + local)."""
    http_tools: list[dict[str, str]] = []
    try:
        # Merge base ai-agent.yaml then local override (same effective set Ava loads).
        merged_in_call: dict[str, Any] = {}
        merged_post: dict[str, Any] = {}
        for path in (
            AVA_ROOT / "config" / "ai-agent.yaml",
            AVA_CONFIG_PATH,
        ):
            if not path.is_file():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            if isinstance(data.get("in_call_tools"), dict):
                merged_in_call.update(data["in_call_tools"])
            if isinstance(data.get("tools"), dict):
                merged_post.update(data["tools"])
        for name, cfg in merged_in_call.items():
            if name in _TOOL_META_SKIP_NAMES:
                continue
            if not isinstance(cfg, dict):
                continue
            http_tools.append(
                {
                    "name": str(name),
                    "group": "http",
                    "label": str(name),
                    "source": "in_call_tools",
                }
            )
        for name, cfg in merged_post.items():
            if name in _TOOL_META_SKIP_NAMES:
                continue
            if not isinstance(cfg, dict):
                continue
            http_tools.append(
                {
                    "name": str(name),
                    "group": "post_call",
                    "label": str(name),
                    "source": "tools",
                }
            )
    except Exception as exc:
        logger.warning("tool catalog yaml read failed: %s", exc)

    in_call = [{**t, "source": "builtin", "phase": "in_call"} for t in _BUILTIN_IN_CALL_TOOLS]
    for t in http_tools:
        phase = "post_call" if t.get("group") == "post_call" else "in_call"
        in_call.append({**t, "phase": phase})

    # Dedup by name, prefer first (builtin) then http
    seen: set[str] = set()
    tools: list[dict[str, Any]] = []
    for t in in_call:
        n = t["name"]
        if n in seen or n in _TOOL_META_SKIP_NAMES:
            continue
        seen.add(n)
        tools.append(_enrich_tool(t))

    dialable = sorted(t["name"] for t in tools if t.get("phase") == "in_call")
    return {
        "ok": True,
        "tools": tools,
        "dialable": dialable,
        "groups": _GROUP_LABELS,
        "default_outbound": ["hangup_call"],
        "note": (
            "В сценарии профиля включайте нужные tools. "
            "На исходящем one-shot dial список можно переопределить на этот звонок."
        ),
    }


def _allowed_dial_tool_names() -> set[str]:
    return set(_tool_catalog()["dialable"])


def _normalize_tool_list(raw: list[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def _resolve_dial_tools(
    *,
    tools: list[str] | None,
    use_knowledge: bool,
) -> tuple[list[str], bool]:
    """Resolve per-call tool allowlist.

    Returns (tools, apply_override). Explicit tools= wins over use_knowledge.
    apply_override=False means dial should leave YAML context tools alone.
    """
    allowed = _allowed_dial_tool_names()
    if tools is not None:
        resolved = _normalize_tool_list(tools)
        if not resolved:
            resolved = ["hangup_call"]
        unknown = [t for t in resolved if t not in allowed]
        if unknown:
            raise HTTPException(
                400,
                f"unknown/non-dialable tools: {unknown}. "
                f"See GET /api/tools (dialable={sorted(allowed)})",
            )
        if "hangup_call" not in resolved and "hangup_call" in allowed:
            resolved.append("hangup_call")
        return resolved, True

    if use_knowledge:
        resolved = ["hangup_call"]
        if "get_company_knowledge" in allowed:
            resolved = ["get_company_knowledge", "hangup_call"]
        return resolved, True

    # No per-call tools override — YAML outbound.tools applies.
    return ["hangup_call"], False


def _compose_outbound_prompt(script: str, *, use_knowledge: bool) -> str:
    body = (script or "").strip()
    if use_knowledge and "get_company_knowledge" not in body and "SECOND BRAIN" not in body.upper():
        body = body + KNOWLEDGE_SCRIPT_FOOTER
    if "НЕ РВИ ТРУБКУ" not in body and "ЗАПРЕЩЕНО вызывать hangup_call" not in body:
        body = body + HANGUP_GUARD_FOOTER
    return body


@app.get("/api/tools")
def api_tools_catalog(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """List Ava tools available for dial / scenario allowlists."""
    _require_token(x_console_token)
    return _tool_catalog()


@app.put("/api/outbound/script")
def api_outbound_script_put(
    body: OutboundScriptUpdate,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Set the FULL outbound conversation context (greeting + script) in one call.

    This is the preferred way to replace the old payouts playbook with your own script.
    Transcripts still land in call_history.db automatically after the call.
    """
    _require_token(x_console_token)
    tools = body.tools
    if tools is None:
        # Global YAML default: hangup only. Calendar stays opt-in via explicit tools=.
        tools = ["hangup_call"]
        if body.use_knowledge:
            tools = ["get_company_knowledge", "hangup_call"]
    prompt = _compose_outbound_prompt(body.script, use_knowledge=body.use_knowledge)
    # Reuse scenario put logic for isolation + YAML write.
    return api_scenario_put(
        ScenarioUpdate(
            context="outbound",
            greeting=body.greeting,
            prompt=prompt,
            tools=tools,
            use_knowledge=body.use_knowledge,
            model=body.model,
            voice=body.voice,
            temperature=body.temperature,
            restart=body.restart,
        ),
        x_console_token,
    )


@app.get("/api/outbound/script")
def api_outbound_script_get(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Read current outbound greeting/script/tools."""
    _require_token(x_console_token)
    payload = _scenario_payload("outbound")
    return {
        "ok": True,
        "greeting": payload.get("greeting"),
        "script": payload.get("prompt"),
        "tools": payload.get("tools"),
        "provider": payload.get("provider"),
        "model": payload.get("model"),
        "voice": payload.get("voice"),
        "temperature": payload.get("temperature"),
        "use_knowledge": "get_company_knowledge" in (payload.get("tools") or []),
        "transcripts": payload.get("transcripts"),
        "how_to_apply": (
            "Outbound YAML playbook is intentionally empty (tools=hangup_call only). "
            "Pass greeting+script on each POST /api/outbound/dial (per-call). "
            "Inbound contexts.default is separate and unchanged. "
            "PUT /api/outbound/script only if you want a global outbound default."
        ),
    }


def _reload_knowledge_service() -> dict[str, Any]:
    try:
        req = urllib.request.Request(KNOWLEDGE_RELOAD_URL, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                return json.loads(raw) if raw else {"ok": True}
            except json.JSONDecodeError:
                return {"ok": True, "raw": raw[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


@app.put("/api/knowledge")
def api_knowledge_put(
    body: KnowledgeUpdate,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    bak = KNOWLEDGE_PATH.with_suffix(KNOWLEDGE_PATH.suffix + ".bak.console")
    if KNOWLEDGE_PATH.is_file():
        bak.write_text(KNOWLEDGE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    KNOWLEDGE_PATH.write_text(body.text, encoding="utf-8")
    # sync bundled copy used by ava-knowledge if present
    bundled = Path("/opt/ava-knowledge/content/quantum_labs.md")
    if bundled.parent.is_dir():
        try:
            bundled.write_text(body.text, encoding="utf-8")
        except OSError as exc:
            logger.warning("could not sync bundled knowledge: %s", exc)
    reload_info: dict[str, Any] = {"skipped": True}
    if body.reload:
        reload_info = _reload_knowledge_service()
    return {
        "ok": True,
        "path": str(KNOWLEDGE_PATH),
        "chars": len(body.text),
        "knowledge_reload": reload_info,
    }


def _role_label(role: str) -> str:
    from transcript_format import role_label

    return role_label(role)


def _format_transcript_preview(hist_raw: Any, limit: int = 320) -> str:
    from transcript_format import format_transcript_preview

    return format_transcript_preview(hist_raw, limit=limit)


def _calls_row_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    hist = data.pop("conversation_history", None)
    data["transcript_preview"] = _format_transcript_preview(hist)
    return data


@app.get("/api/calls")
def api_calls(
    limit: int = 30,
    context: str | None = None,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    limit = max(1, min(limit, 200))
    if not CALL_HISTORY_DB.is_file():
        return {"calls": [], "total": 0}
    conn = sqlite3.connect(str(CALL_HISTORY_DB))
    conn.row_factory = sqlite3.Row
    try:
        if context:
            total = int(
                conn.execute(
                    "SELECT COUNT(*) AS c FROM call_records WHERE context_name = ?",
                    (context,),
                ).fetchone()["c"]
            )
            rows = conn.execute(
                """
                SELECT call_id, caller_number, caller_name, start_time, end_time,
                       duration_seconds, provider_name, context_name, outcome,
                       conversation_history
                FROM call_records
                WHERE context_name = ?
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (context, limit),
            ).fetchall()
        else:
            total = int(conn.execute("SELECT COUNT(*) AS c FROM call_records").fetchone()["c"])
            rows = conn.execute(
                """
                SELECT call_id, caller_number, caller_name, start_time, end_time,
                       duration_seconds, provider_name, context_name, outcome,
                       conversation_history
                FROM call_records
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return {
            "total": total,
            "calls": [_calls_row_dict(r) for r in rows],
            "filter_context": context,
        }
    finally:
        conn.close()


@app.get("/api/calls/{call_id}")
def api_call_detail(
    call_id: str,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Full transcript + metadata for one call (inbound or outbound)."""
    _require_token(x_console_token)
    if not CALL_HISTORY_DB.is_file():
        raise HTTPException(404, "call_history.db missing")
    conn = sqlite3.connect(str(CALL_HISTORY_DB))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT call_id, caller_number, caller_name, start_time, end_time,
                   duration_seconds, provider_name, context_name, outcome,
                   error_message, conversation_history, tool_calls, total_turns
            FROM call_records
            WHERE call_id = ?
            LIMIT 1
            """,
            (call_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, f"call_id not found: {call_id}")
        data = dict(row)
        hist_raw = data.get("conversation_history") or "[]"
        try:
            data["conversation"] = json.loads(hist_raw) if isinstance(hist_raw, str) else hist_raw
        except json.JSONDecodeError:
            data["conversation"] = []
            data["conversation_raw"] = hist_raw
        tools_raw = data.get("tool_calls") or "[]"
        try:
            data["tools"] = json.loads(tools_raw) if isinstance(tools_raw, str) else tools_raw
        except json.JSONDecodeError:
            data["tools"] = []
        data.pop("conversation_history", None)
        data.pop("tool_calls", None)
        # Normalized turns for UI tables (role label + text)
        turns_out: list[dict[str, Any]] = []
        for i, item in enumerate(data.get("conversation") or []):
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("text") or "").strip()
            if not content:
                continue
            turns_out.append(
                {
                    "n": i + 1,
                    "role": str(item.get("role") or ""),
                    "who": _role_label(str(item.get("role") or "")),
                    "text": content,
                }
            )
        data["turns"] = turns_out
        return {"ok": True, "call": data}
    finally:
        conn.close()


@app.get("/api/secrets-checklist")
def api_secrets_checklist(x_console_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_console_token)
    ava = _read_env_file(AVA_ENV_PATH)
    mailer = _read_env_file(MAILER_ENV_PATH)
    keys = [
        ("ava", "OPENAI_API_KEY", ava),
        ("ava", "ASTERISK_ARI_PASSWORD", ava),
        ("ava", "AAVA_OUTBOUND_DIAL_CONTEXT", ava),
        ("mailer", "WEBHOOK_TOKEN", mailer),
        ("mailer", "MAIL_USERNAME", mailer),
        ("mailer", "MAIL_PASSWORD", mailer),
        ("mailer", "MAILRU_CALDAV_PASSWORD", mailer),
        ("mailer", "YANDEX_OAUTH_CLIENT_SECRET", mailer),
        ("mailer", "OUTREACH_CRM_TOKEN", mailer),
    ]
    items = []
    for scope, key, src in keys:
        val = (src.get(key) or "").strip()
        items.append(
            {
                "scope": scope,
                "key": key,
                "present": bool(val),
                "hint": (val[:2] + "…" + val[-2:]) if len(val) > 6 else ("set" if val else "missing"),
            }
        )
    yandex = Path("/opt/ava-mailer/yandex_oauth_tokens.json")
    items.append(
        {
            "scope": "mailer",
            "key": "yandex_oauth_tokens.json",
            "present": yandex.is_file() and yandex.stat().st_size > 10,
            "hint": "file" if yandex.is_file() else "missing",
        }
    )
    return {"items": items}


@app.post("/api/actions/restart-engine")
def api_restart_engine(x_console_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_console_token)
    return _restart_ai_engine()


@app.post("/api/actions/backup")
def api_backup(x_console_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_console_token)
    if not BACKUP_SCRIPT.is_file():
        raise HTTPException(404, f"backup script missing: {BACKUP_SCRIPT}")
    rc, out = _run(["bash", str(BACKUP_SCRIPT)], timeout=600)
    return {"ok": rc == 0, "exit_code": rc, "output": out[-4000:]}


@app.post("/api/actions/reload-dialplan")
def api_reload_dialplan(x_console_token: str | None = Header(default=None)) -> dict[str, Any]:
    _require_token(x_console_token)
    ensure = AVA_ROOT / "scripts/ensure_asterisk_config.sh"
    steps = []
    if ensure.is_file():
        rc, out = _run(["bash", str(ensure)], timeout=30)
        steps.append({"cmd": "ensure_asterisk_config", "ok": rc == 0, "output": out[-1000:]})
    # Force copy from canon if console shipped updated dialplan into AVA config
    rc2, out2 = _run(["asterisk", "-rx", "dialplan reload"], timeout=15)
    steps.append({"cmd": "dialplan reload", "ok": rc2 == 0, "output": out2[-500:]})
    return {"ok": all(s["ok"] for s in steps), "steps": steps}


@app.post("/api/outbound/dial")
def api_outbound_dial(
    body: DialRequest,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """One-shot outbound with optional per-call script/greeting.

    Pass ``script`` + ``greeting`` to override the YAML outbound playbook for THIS
    call only (no restart, inbound untouched). Transcripts still go to call_history.db.
    """
    _require_token(x_console_token)
    if not OUTBOUND_ENABLED:
        raise HTTPException(403, "OUTBOUND_ENABLED=false")
    phone = _normalize_phone(body.phone)
    context = _normalize_ai_context(body.context or OUTBOUND_AI_CONTEXT)
    # Resolve provider from the selected profile YAML so dial never borrows inbound settings.
    try:
        yaml_ctx = ((_load_yaml().get("contexts") or {}).get(context) or {})
        yaml_provider = (yaml_ctx.get("provider") or "").strip()
    except Exception:
        yaml_provider = ""
    provider = (
        (body.provider or "").strip()
        or yaml_provider
        or _dedicated_provider_name(context)
    )
    cid_num = (body.caller_id_num or OUTBOUND_CALLER_ID_NUM).strip()
    cid_name = (body.caller_id_name or OUTBOUND_CALLER_ID_NAME).strip()

    ava_env = _read_env_file(AVA_ENV_PATH)
    ari_user = ava_env.get("ASTERISK_ARI_USERNAME") or "asterisk-ai-voice-agent"
    ari_pass = ava_env.get("ASTERISK_ARI_PASSWORD") or ""
    ari_host = ava_env.get("ASTERISK_HOST") or "127.0.0.1"
    ari_port = ava_env.get("ASTERISK_ARI_PORT") or "8088"
    if not ari_pass:
        raise HTTPException(500, "ASTERISK_ARI_PASSWORD missing in AVA .env")

    endpoint = f"PJSIP/{phone}@mango-employee"
    import base64
    import uuid
    from urllib.parse import urlencode

    vars_payload: dict[str, str] = {
        "AI_CONTEXT": context,
        "AI_PROVIDER": provider,
        "AAVA_OUTBOUND": "1",
        "AAVA_OUTBOUND_PHONE": phone,
        "AAVA_OUTBOUND_SCENARIO": context,
    }

    per_call_script = (body.script or "").strip()
    per_call_greeting = (body.greeting or "").strip()
    per_call_tools, tools_override = _resolve_dial_tools(
        tools=body.tools,
        use_knowledge=bool(body.use_knowledge),
    )
    want_knowledge = "get_company_knowledge" in per_call_tools or bool(body.use_knowledge)
    script_file_host: str | None = None
    script_file_container: str | None = None
    # Write per-call payload when any of script/greeting/tools override is present.
    if per_call_script or per_call_greeting or tools_override:
        if per_call_script:
            per_call_script = _compose_outbound_prompt(
                per_call_script, use_knowledge=want_knowledge
            )
        script_dir = AVA_ROOT / "data" / "call_scripts"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_id = uuid.uuid4().hex
        script_path = script_dir / f"{script_id}.json"
        payload_doc: dict[str, Any] = {
            "greeting": per_call_greeting,
            "script": per_call_script,
            "phone": phone,
            "context": context,
            "created_at": int(time.time()),
        }
        if tools_override:
            payload_doc["tools"] = per_call_tools
        script_path.write_text(
            json.dumps(payload_doc, ensure_ascii=False),
            encoding="utf-8",
        )
        script_file_host = str(script_path)
        # Bind-mount: /root/ava/data → /app/data inside ai_engine
        script_file_container = f"/app/data/call_scripts/{script_id}.json"
        vars_payload["AAVA_CALL_SCRIPT_FILE"] = script_file_container
        if per_call_greeting:
            # Small greeting also as channel var (belt & suspenders)
            vars_payload["AAVA_CALL_GREETING"] = per_call_greeting[:500]
        custom: dict[str, Any] = {
            "__script__": per_call_script,
            "__greeting__": per_call_greeting,
        }
        if tools_override:
            custom["__tools__"] = per_call_tools
        vars_payload["AAVA_CUSTOM_VARS_JSON"] = json.dumps(custom, ensure_ascii=False)

    cli_num = cid_num or "79699665899"
    cli_name = cid_name or "Quantum Labs"
    query_params: dict[str, str] = {
        "endpoint": endpoint,
        "app": OUTBOUND_STASIS_APP,
        "callerId": f"{cli_name} <{cli_num}>",
        "timeout": "60",
    }
    query = urlencode(query_params)
    url = f"http://{ari_host}:{ari_port}/ari/channels?{query}"
    auth = base64.b64encode(f"{ari_user}:{ari_pass}".encode()).decode()
    body_bytes = json.dumps({"variables": vars_payload}).encode()
    req = urllib.request.Request(
        url,
        data=body_bytes,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(raw) if raw else {}
            return {
                "ok": True,
                "phone": phone,
                "endpoint": endpoint,
                "channel_id": payload.get("id"),
                "state": payload.get("state"),
                "context": context,
                "provider": provider,
                "per_call_script": bool(per_call_script),
                "per_call_greeting": bool(per_call_greeting),
                "per_call_tools": per_call_tools if tools_override else None,
                "tools_override": tools_override,
                "script_file": script_file_host,
                "script_chars": len(per_call_script or ""),
            }
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:800]
        raise HTTPException(e.code, f"ARI originate failed: {detail}") from e
    except urllib.error.URLError as e:
        raise HTTPException(502, f"ARI unreachable: {e}") from e


@app.post("/api/outbound/callback")
def api_outbound_callback(
    body: CallbackRequest,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Outbound via Mango VPBX API callback (bypasses SIP PSTN 403 on Beget).

    Flow: Mango rings extension (Asterisk/AVA answers) → Mango dials PSTN to_number.
    """
    _require_token(x_console_token)
    if not OUTBOUND_ENABLED:
        raise HTTPException(403, "OUTBOUND_ENABLED=false")
    phone = _normalize_phone(body.phone)
    extension = (body.extension or MANGO_CALLBACK_EXTENSION).strip() or "12"
    line = (body.line_number or OUTBOUND_CALLER_ID_NUM).strip() or "79699665899"
    cmd_id = (body.command_id or f"qc-{int(time.time())}-{phone[-4:]}").strip()
    payload = {
        "command_id": cmd_id,
        "from": {"extension": extension},
        "to_number": phone,
        "line_number": line,
    }
    code, resp = _mango_api_post("/commands/callback", payload)
    result = resp.get("result") if isinstance(resp, dict) else None
    ok = code == 200 and str(result) in {"1000", "1000.0", 1000}
    return {
        "ok": ok,
        "mode": "mango_api_callback",
        "http": code,
        "phone": phone,
        "extension": extension,
        "line_number": line,
        "command_id": cmd_id,
        "mango": resp,
        "note": (
            "Mango first calls extension (AVA/Asterisk), then PSTN. "
            "Success = mobile rings, not only result=1000."
        ),
    }


def _campaign_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if CAMPAIGN_TOKEN:
        h["X-Webhook-Token"] = CAMPAIGN_TOKEN
    return h


def _campaign_request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    if not CAMPAIGN_BASE:
        raise HTTPException(503, "CAMPAIGN_BASE not configured")
    url = f"{CAMPAIGN_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers=_campaign_headers()
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(exc.code, f"campaign: {err[:500]}") from exc
    except Exception as exc:
        raise HTTPException(502, f"campaign unreachable: {exc}") from exc


class CampaignScriptUpdate(BaseModel):
    greeting: str | None = None
    script: str | None = None
    tools: list[str] | None = None


class CampaignStartBody(BaseModel):
    max_calls: int = Field(default=5, ge=0, le=200)
    sheet: str | None = None
    dry_run: bool | None = None


@app.get("/api/campaign/script")
def api_campaign_script_get(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Playbook for Google Sheets payouts campaign (not YAML outbound profile)."""
    _require_token(x_console_token)
    return _campaign_request("GET", "/api/campaign/script")


@app.put("/api/campaign/script")
def api_campaign_script_put(
    body: CampaignScriptUpdate,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return _campaign_request("PUT", "/api/campaign/script", body=payload)


@app.post("/api/campaign/script/reset")
def api_campaign_script_reset(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    return _campaign_request("POST", "/api/campaign/script/reset", body={})


@app.get("/api/campaign/preview")
def api_campaign_preview(
    limit: int = 20,
    sheet: str | None = None,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    q = f"?limit={max(1, min(limit, 200))}"
    if sheet:
        q += f"&sheet={urllib.parse.quote(sheet)}"
    return _campaign_request("GET", f"/api/campaign/preview{q}")


@app.get("/api/campaign/results")
def api_campaign_results(
    limit: int = 50,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    q = f"?limit={max(1, min(limit, 500))}"
    return _campaign_request("GET", f"/api/campaign/results{q}")


@app.get("/api/campaign/status")
def api_campaign_status(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    return _campaign_request("GET", "/api/campaign/status")


@app.post("/api/campaign/start")
def api_campaign_start(
    body: CampaignStartBody,
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    return _campaign_request(
        "POST",
        "/api/campaign/start",
        body=body.model_dump(exclude_none=True),
    )


@app.post("/api/campaign/stop")
def api_campaign_stop(
    x_console_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_token(x_console_token)
    return _campaign_request("POST", "/api/campaign/stop", body={})


# ---------------------------------------------------------------------------
# Outreach — reverse proxy (full admin UI embedded in Console)
# ---------------------------------------------------------------------------


def _outreach_proxy_headers() -> dict[str, str]:
    tok = _load_outreach_ui_token()
    h = {"Accept": "application/json"}
    if tok:
        h["X-Outreach-Token"] = tok
    return h


@app.api_route(
    "/api/outreach/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def api_outreach_proxy(full_path: str, request: Request):
    """Proxy authenticated Console sessions to ava-outreach (:8012).

    Browser never sees OUTREACH_UI_TOKEN — Console injects it server-side.
    """
    from fastapi.responses import Response

    if not _request_authenticated(request):
        raise HTTPException(401, "unauthorized")
    if not OUTREACH_BASE:
        raise HTTPException(503, "OUTREACH_BASE not configured")
    tok = _load_outreach_ui_token()
    if not tok:
        raise HTTPException(
            503,
            "OUTREACH_UI_TOKEN not configured (set in console .env or /opt/ava-outreach/.env)",
        )

    qs = request.url.query
    url = f"{OUTREACH_BASE}/{full_path.lstrip('/')}"
    if qs:
        url = f"{url}?{qs}"

    body = await request.body()
    headers = _outreach_proxy_headers()
    ctype = request.headers.get("content-type")
    if ctype:
        headers["Content-Type"] = ctype
    elif body:
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(
        url,
        data=body if body else None,
        method=request.method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return Response(
                content=raw,
                status_code=resp.status,
                media_type=resp.headers.get("Content-Type") or "application/json",
            )
    except urllib.error.HTTPError as exc:
        err = exc.read()
        return Response(
            content=err,
            status_code=exc.code,
            media_type=exc.headers.get("Content-Type") or "application/json",
        )
    except Exception as exc:
        raise HTTPException(502, f"outreach unreachable: {exc}") from exc
