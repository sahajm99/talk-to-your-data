"""Shared request helpers for the API routes and pages."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import Request

from app.models import AboutInfo, DocumentInfo
from app.services.generation import generation_status
from app.services.sessions import PRELOADED_SCOPE

ROOT = Path(__file__).resolve().parents[2]
EVAL_RESULTS = ROOT / "eval" / "results.json"

LIMITS = [
    "The embedding model is small (BAAI/bge-small-en-v1.5, 384 dimensions) so it runs on a free CPU instance.",
    "There is no reranker: the top five passages come straight from keyword and vector search fused by rank.",
    "Documents are cut into 300-word passages, so an answer spread across distant pages can be missed.",
    "Uploads live only in your browser session and are deleted after an hour idle or when the server restarts.",
    "Questions are rate limited per visitor and per day to keep the free language-model quota alive.",
    "The free host sleeps when idle, so the first request after a quiet period can take up to a minute.",
]


class LockedStore:
    """Serialises every call on the shared SQLite connection; embedding happens outside it."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._store, name)
        if not callable(attr):
            return attr

        def locked(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return attr(*args, **kwargs)

        return locked


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def visible_documents(state: Any, session_id: str) -> list[DocumentInfo]:
    docs = state.store.list_documents([PRELOADED_SCOPE, session_id])
    return sorted(
        docs,
        key=lambda d: (d.scope != PRELOADED_SCOPE, d.title if d.scope == PRELOADED_SCOPE else d.created_at),
    )


def load_eval() -> dict | None:
    try:
        return json.loads(EVAL_RESULTS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def about_info(state: Any) -> AboutInfo:
    settings = state.settings
    mode, model = generation_status(settings)
    return AboutInfo(
        generation_mode=mode,
        model=model,
        embed_model=settings.embed_model,
        documents=list(state.store.list_documents([PRELOADED_SCOPE])),
        eval=load_eval(),
        rate_limit={
            "questions": settings.rate_limit_questions,
            "window_seconds": settings.rate_limit_window_seconds,
            "daily_cap": settings.daily_question_cap,
        },
    )
