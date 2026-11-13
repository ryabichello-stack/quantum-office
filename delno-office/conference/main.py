"""
ava-conference — multi-provider conference broker + optional email invites.

Providers: yandex/telemost | google_meet | zoom | teams | jitsi
Tools-first: stub join URLs without provider credentials.

Does NOT own Bitrix outreach, Asterisk, or Polyhub trading.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

load_dotenv()

import invites
import providers
import yandex_oauth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-conference")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "ava-conference"

app = FastAPI(title="Quantum Labs Conference", version="0.2.0")


def _check_token(
    x_webhook_token: Optional[str] = None,
    token_query: str = "",
) -> None:
    provided = (x_webhook_token or token_query or "").strip()
    # Fail closed: an empty token must not open the API.
    if not WEBHOOK_TOKEN or provided != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class ConferenceCreateRequest(BaseModel):
    title: str = Field(default="Встреча Quantum Labs", max_length=200)
    provider: Optional[str] = Field(
        default=None,
        description="yandex | google_meet | zoom | teams | jitsi",
    )
    invitees: List[str] = Field(default_factory=list, description="Email list")
    message: str = Field(default="", max_length=2000, description="Note in invite email")
    when_text: str = Field(
        default="",
        max_length=200,
        description="Human-readable time, e.g. 'сегодня 16:30 МСК'",
    )
    waiting_room_level: Optional[str] = Field(
        default=None,
        description="PUBLIC | ADMINS | USERS — Telemost waiting room",
    )
    send_invites: bool = Field(default=True)


class ConferenceCreateResponse(BaseModel):
    ok: bool
    conference_id: str = ""
    join_url: str = ""
    title: str = ""
    provider: str = ""
    invites: List[dict] = Field(default_factory=list)
    error: str = ""
    message: str = ""
    stub: bool = False


@app.get("/health")
def health():
    oauth = yandex_oauth.oauth_status()
    has_token = bool(oauth.get("has_access_token") or oauth.get("static_token_set"))
    status = providers.providers_status()
    any_live = any(p["configured"] for p in status["providers"])
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "telemost_enabled": True,  # legacy field
        "smtp_configured": invites.smtp_configured(),
        "oauth_configured": oauth.get("configured"),
        "oauth_has_token": has_token,
        "stub_mode": not any_live,
        "creds_policy": "tools_first",
        **status,
    }


@app.get("/api/conferences/providers")
def conference_providers(x_webhook_token: Optional[str] = Header(None)):
    _check_token(x_webhook_token)
    return {"ok": True, **providers.providers_status()}


@app.post("/api/conferences")
def create_conference(
    req: ConferenceCreateRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """
    On-demand conference:
    1) create meeting link via selected provider
    2) optional email invites
    """
    _check_token(x_webhook_token)

    title = (req.title or "").strip() or "Встреча Quantum Labs"
    try:
        provider = providers.get_provider(req.provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    created = provider.create(title=title, waiting_room_level=req.waiting_room_level)
    join_url = str(created.get("join_url") or "")
    conf_id = str(created.get("conference_id") or "")
    stub = bool(created.get("stub"))
    if not join_url:
        return JSONResponse(
            status_code=502,
            content=ConferenceCreateResponse(
                ok=False,
                title=title,
                provider=provider.name,
                error=str(created.get("error") or "create_failed"),
                message=str(created.get("message") or "Не удалось создать конференцию"),
            ).model_dump(),
        )

    invite_results: List[dict] = []
    if req.send_invites and req.invitees and not stub:
        invite_results = invites.send_invites(
            invitees=req.invitees,
            title=title,
            join_url=join_url,
            when_text=req.when_text,
            host_note=req.message,
        )
    elif req.send_invites and req.invitees and stub:
        invite_results = [
            {"email": e, "sent": False, "stub": True, "error": "smtp_skipped_stub"}
            for e in req.invitees
        ]

    sent_ok = sum(1 for r in invite_results if r.get("sent"))
    msg = str(created.get("message") or f"Конференция создана: {join_url}")
    if req.invitees:
        msg += f". Приглашения: {sent_ok}/{len(req.invitees)} отправлено"

    return ConferenceCreateResponse(
        ok=True,
        conference_id=conf_id,
        join_url=join_url,
        title=title,
        provider=provider.name,
        invites=invite_results,
        message=msg,
        stub=stub,
    ).model_dump()


# ---- Yandex OAuth (same flow as mailer; tokens owned by this service) ----


@app.get("/oauth/yandex/status")
def yandex_oauth_status(x_webhook_token: Optional[str] = Header(None)):
    _check_token(x_webhook_token)
    status = yandex_oauth.oauth_status()
    status["authorize_url_hint"] = "/oauth/yandex/start?token=<WEBHOOK_TOKEN>"
    return status


@app.get("/oauth/yandex/start")
def yandex_oauth_start(token: str = ""):
    _check_token(token_query=token)
    if not yandex_oauth.oauth_configured():
        raise HTTPException(
            status_code=500,
            detail="Set YANDEX_OAUTH_CLIENT_ID / SECRET / REDIRECT_URI in .env",
        )
    return RedirectResponse(yandex_oauth.build_authorize_url(), status_code=302)


@app.get("/oauth/yandex/callback")
def yandex_oauth_callback(code: str = "", error: str = "", error_description: str = ""):
    return _yandex_oauth_finish(code=code, error=error, error_description=error_description)


@app.get("/oauth/yandex/manual", response_class=HTMLResponse)
def yandex_oauth_manual_page(token: str = ""):
    _check_token(token_query=token)
    auth_url = yandex_oauth.build_authorize_url()
    return f"""<!doctype html><html><body style="font-family:sans-serif;max-width:640px;margin:2rem auto">
    <h1>Yandex OAuth (conference)</h1>
    <p><a href="{auth_url}">Открыть авторизацию Яндекса</a></p>
    <form method="post" action="/oauth/yandex/manual?token={token}">
      <label>code <input name="code" style="width:100%"></label>
      <button type="submit">Обменять code</button>
    </form>
    </body></html>"""


@app.post("/oauth/yandex/manual", response_class=HTMLResponse)
async def yandex_oauth_manual_submit(request: Request, token: str = ""):
    _check_token(token_query=token)
    form = await request.form()
    code = str(form.get("code") or "")
    return _yandex_oauth_finish(code=code)


def _yandex_oauth_finish(
    code: str = "",
    error: str = "",
    error_description: str = "",
):
    if error:
        return HTMLResponse(
            f"<h1>OAuth error</h1><pre>{error}: {error_description}</pre>",
            status_code=400,
        )
    result = yandex_oauth.exchange_authorization_code(code)
    if not result.get("ok"):
        return HTMLResponse(
            f"<h1>Exchange failed</h1><pre>{result}</pre>",
            status_code=400,
        )
    return HTMLResponse(
        "<h1>OK</h1><p>Refresh-токен сохранён. "
        "Теперь <code>POST /api/conferences</code> с <code>provider=yandex</code> "
        "создаёт ссылки Телемост.</p>"
    )
