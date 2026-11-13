import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.operator.tools import register_builtin_tools
from app.scripts.seed import seed_demo_tenant

logger = logging.getLogger("delno.schedule")


async def _schedule_ticker_loop() -> None:
    """Background: claim due hermes.tasks and run them via the tool agent."""
    await asyncio.sleep(15)
    while True:
        try:
            from app.services.agent_schedule import tick_due_tasks

            db = SessionLocal()
            try:
                out = await asyncio.to_thread(tick_due_tasks, db, limit=3)
                if out.get("claimed"):
                    logger.info("schedule tick claimed=%s", out.get("claimed"))
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("schedule ticker failed")
        await asyncio.sleep(60)


async def _reconcile_runs_loop() -> None:
    """Close stale agent_runs that no longer have a live Hermes upstream run."""
    await asyncio.sleep(45)
    while True:
        try:
            from app.services.hermes_nous.reconcile import reconcile_stale_runs

            db = SessionLocal()
            try:
                out = await asyncio.to_thread(
                    reconcile_stale_runs, db, older_than_minutes=30, limit=40
                )
                if out.get("closed"):
                    logger.info(
                        "hermes reconcile closed=%s checked=%s",
                        out.get("closed"),
                        out.get("checked"),
                    )
            finally:
                db.close()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("hermes reconcile ticker failed")
        await asyncio.sleep(300)


def _cors_kwargs() -> dict:
    settings = get_settings()
    origins_raw = (settings.cors_allow_origins or "").strip()
    if origins_raw:
        origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
        return {
            "allow_origins": origins,
            "allow_credentials": bool(getattr(settings, "cors_allow_credentials", False)),
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    return {
        "allow_origin_regex": (
            r"https://([a-z0-9-]+\.)?dlno\.ru"
            r"|https://a\.47z\.ru"
            r"|http://localhost(:\d+)?"
            r"|http://127\.0\.0\.1(:\d+)?"
            r"|http://161\.104\.89\.123(:\d+)?"
        ),
        "allow_credentials": False,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


@asynccontextmanager
async def lifespan(_app: FastAPI):
    import app.models  # noqa: F401 — register ORM tables for create_all

    Base.metadata.create_all(bind=engine)
    seed_demo_tenant()
    register_builtin_tools()
    import app.services.lead_email  # noqa: F401 — register SMTP notify hooks
    ticker = asyncio.create_task(_schedule_ticker_loop(), name="hermes-schedule-ticker")
    reconcile = asyncio.create_task(_reconcile_runs_loop(), name="hermes-reconcile-runs")
    try:
        yield
    finally:
        ticker.cancel()
        reconcile.cancel()
        for task in (ticker, reconcile):
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="DELNO API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, **_cors_kwargs())
app.include_router(v1_router)


@app.get("/health")
def health_root() -> dict:
    return {"ok": True, "service": "delno-api"}
