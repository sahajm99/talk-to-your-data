"""GET /api/health and GET /api/about."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import about_info
from app.models import AboutInfo
from app.services.generation import generation_status

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health")
def health(request: Request) -> dict:
    state = request.app.state
    mode, model = generation_status(state.settings)
    return {"status": "ok", **state.store.counts(), "generation_mode": mode, "model": model}


@router.get("/about", response_model=AboutInfo)
def about(request: Request) -> AboutInfo:
    return about_info(request.app.state)
