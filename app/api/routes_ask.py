"""POST /api/ask: retrieve, then generate or extract."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import client_ip, visible_documents
from app.ingestion.retrieval import hybrid_search
from app.models import AskRequest, AskResponse, Citation
from app.services.generation import answer
from app.services.sessions import PRELOADED_SCOPE

router = APIRouter(prefix="/api", tags=["ask"])


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, request: Request, response: Response) -> AskResponse:
    state = request.app.state
    settings = state.settings
    started = time.perf_counter()
    session_id = state.sessions.get_or_create(request, response)

    question = body.question.strip()
    if not question:
        raise HTTPException(400, "Type a question first.")

    doc_ids = None
    if body.document_ids:
        visible = {d.id for d in visible_documents(state, session_id)}
        if any(d not in visible for d in body.document_ids):
            raise HTTPException(404, "One of the selected documents is no longer available. Reload the page.")
        doc_ids = list(dict.fromkeys(body.document_ids))

    ip = client_ip(request)
    allowed, reason = state.limiter.check(ip)
    if not allowed:
        retry = state.limiter.retry_after(ip)
        raise HTTPException(
            429, f"Slow down: {reason}. Try again in {retry} seconds.", headers={"Retry-After": str(retry)}
        )

    hits = hybrid_search(
        state.store,
        state.embedder,
        question,
        [PRELOADED_SCOPE, session_id],
        k=settings.top_k,
        candidates=settings.candidates_per_source,
        mode=body.mode,
        doc_ids=doc_ids,
    )
    result = answer(question, hits, settings)
    return AskResponse(
        answer=result.text,
        mode=result.mode,
        model=result.model,
        citations=[
            Citation(
                n=i,
                chunk_id=h.chunk.id,
                doc_id=h.chunk.doc_id,
                doc_title=h.chunk.doc_title,
                idx=h.chunk.idx,
                text=h.chunk.text,
            )
            for i, h in enumerate(hits, start=1)
        ],
        retrieval=[h.to_retrieval_hit() for h in hits],
        latency_ms=int((time.perf_counter() - started) * 1000),
    )
