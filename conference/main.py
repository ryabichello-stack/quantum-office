"""
ava-conference — standalone Telemost + email invites service.

Architectural boundary:
- Creates Yandex Telemost join links on demand
- Sends invite emails to a list of participants
- Does NOT own Bitrix outreach, Asterisk, or Polyhub trading

Voice / office later: AVA tool → POST /api/conferences
Mailer calendar booking can keep its own path or call this service.
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
import telemost
import yandex_oauth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-conference")

WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()
SERVICE_NAME = "ava-conference"

app = FastAPI(title="Quantum Labs Conference", version="0.1.0")


def _check_token(
    x_webhook_token: Optional[str] = None,
    token_query: str = "",
) -> None:
    if not WEBHOOK_TOKEN:
        return
    provided = (x_webhook_token or token_query or "").strip()
    if provided != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class ConferenceCreateRequest(BaseModel):
    title: str = Field(default="Встреча Quantum Labs", max_length=200)
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
    invites: List[dict] = Field(default_factory=list)
    error: str = ""
    message: str = ""


@app.get("/health")
def health():
    oauth = yandex_oauth.oauth_status()
    return {
        "ok": True,
        "service": SERVICE_NAME,
        "telemost_enabled": telemost.TELEMOST_ENABLED,
        "smtp_configured": invites.smtp_configured(),
        "oauth_configured": oauth.get("configured"),
        "oauth_has_token": bool(oauth.get("has_access_token") or oauth.get("static_token_set")),
    }


@app.post("/api/conferences", response_model=ConferenceCreateResponse)
def create_conference(
    req: ConferenceCreateRequest,
    x_webhook_token: Optional[str] = Header(None),
):
    """
    On-demand conference:
    1) create Telemost link
    2) email invites to invitees[]
    """
    _check_token(x_webhook_token)

    title = (req.title or "").strip() or "Встреча Quantum Labs"
    conf_id, join_url, err = telemost.create_conference(
        title=title,
        waiting_room_level=req.waiting_room_level,
    )
    if not join_url:
        return JSONResponse(
            status_code=502,
            content=ConferenceCreateResponse(
                ok=False,
                title=title,
                error=err or "telemost_create_failed",
                message="Не удалось создать конференцию в Яндекс Телемост",
            ).model_dump(),
        )

    invite_results: List[dict] = []
    if req.send_invites and req.invitees:
        invite_results = invites.send_invites(
            invitees=req.invitees,
            title=title,
            join_url=join_url,
            when_text=req.when_text,
            host_note=req.message,
        )

    sent_ok = sum(1 for r in invite_results if r.get("sent"))
    msg = f"Конференция создана: {join_url}"
    if req.invitees:
        msg += f". Приглашения: {sent_ok}/{len(req.invitees)} отправлено"

    return ConferenceCreateResponse(
        ok=True,
        conference_id=conf_id or "",
        join_url=join_url,
        title=title,
        invites=invite_results,
        message=msg,
    )


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
        "Теперь <code>POST /api/conferences</code> создаёт ссылки Телемост.</p>"
    )
