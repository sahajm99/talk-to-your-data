"""FastAPI application: lifespan wiring, API routers and the two pages."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import routes_ask, routes_health, routes_ingest
from app.api.deps import LIMITS, LockedStore, about_info, visible_documents
from app.config import get_settings
from app.ingestion.embedder import get_embedder
from app.ingestion.store import SqliteStore
from app.services.generation import generation_status, get_generator
from app.services.ratelimit import RateLimiter
from app.services.sessions import SessionManager, purge_all

APP_DIR = Path(__file__).resolve().parent
SWEEP_SECONDS = 300
log = logging.getLogger("app")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _warm_up(state) -> None:
    state.embedder.embed_query("warm up")
    gen = get_generator(state.settings)
    if gen is not None:
        try:
            gen.model()
        except Exception as exc:
            log.warning("Groq model lookup failed at startup: %s", exc)


async def _sweeper(app: FastAPI) -> None:
    while True:
        await asyncio.sleep(SWEEP_SECONDS)
        with contextlib.suppress(Exception):
            removed = await run_in_threadpool(app.state.sessions.sweep, app.state.store)
            if removed:
                log.info("expired session documents deleted: %d", removed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    embedder = get_embedder(settings)
    if not Path(settings.index_path).exists():
        log.warning("No index at %s; run `uv run python -m app.ingestion.preload` first", settings.index_path)
    store = SqliteStore(settings.index_path, embedder.dim)
    purged = purge_all(store)
    if purged:
        log.info("uploads left from a previous run deleted: %d", purged)
    state = app.state
    state.settings, state.embedder, state.store = settings, embedder, LockedStore(store)
    state.sessions = SessionManager(settings.session_ttl_minutes)
    state.limiter = RateLimiter(
        settings.rate_limit_questions, settings.rate_limit_window_seconds, settings.daily_question_cap
    )
    await run_in_threadpool(_warm_up, state)
    sweeper = asyncio.create_task(_sweeper(app))
    try:
        yield
    finally:
        sweeper.cancel()
        store.close()


app = FastAPI(title="Talk To Your Data", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
app.include_router(routes_ask.router)
app.include_router(routes_ingest.router)
app.include_router(routes_health.router)


def _base_context(request: Request) -> dict:
    settings = request.app.state.settings
    return {"public_url": settings.public_url, "host": "render" if os.environ.get("RENDER") else "local"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    state = request.app.state
    session_id, _ = state.sessions.resolve(request)
    mode, model = generation_status(state.settings)
    context = _base_context(request) | {
        "documents": visible_documents(state, session_id),
        "generation_mode": mode,
        "model": model,
        "max_upload_mb": state.settings.max_upload_bytes / 1e6,
    }
    resp = templates.TemplateResponse(request, "index.html", context)
    state.sessions.set_cookie(resp, session_id, request)
    return resp


@app.get("/about", response_class=HTMLResponse, include_in_schema=False)
def about(request: Request):
    context = _base_context(request) | {"about": about_info(request.app.state), "limits": LIMITS}
    return templates.TemplateResponse(request, "about.html", context)
