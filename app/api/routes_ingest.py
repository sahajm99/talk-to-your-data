"""POST /api/upload and GET /api/documents. Uploads live only in the session scope."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.api.deps import visible_documents
from app.ingestion.file_types import guess_file_type
from app.ingestion.loaders import RawDocument
from app.ingestion.pipeline import EmptyDocumentError, ingest_raw_document
from app.models import DocumentInfo

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["documents"])

ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
MAX_UPLOADS_PER_SESSION = 5


@router.get("/documents", response_model=list[DocumentInfo])
def documents(request: Request, response: Response) -> list[DocumentInfo]:
    session_id = request.app.state.sessions.get_or_create(request, response)
    return visible_documents(request.app.state, session_id)


@router.post("/upload", response_model=DocumentInfo)
async def upload(request: Request, response: Response, file: UploadFile = File(...)) -> DocumentInfo:
    state = request.app.state
    settings = state.settings
    session_id = state.sessions.get_or_create(request, response)

    name = Path(file.filename or "upload").name
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, "Upload a PDF, DOCX, TXT or Markdown file.")
    data = await file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, f"That file is over the {settings.max_upload_bytes / 1e6:g} MB limit.")
    if len(state.store.list_documents([session_id])) >= MAX_UPLOADS_PER_SESSION:
        raise HTTPException(
            429, f"You can keep up to {MAX_UPLOADS_PER_SESSION} uploaded documents in one session."
        )

    raw = RawDocument(
        project_id=session_id,
        source_id=Path(name).stem,
        file_type=guess_file_type(name, file.content_type),
        file_name=name,
        bytes=data,
        metadata={"file_size": len(data)},
    )
    try:
        doc = await run_in_threadpool(
            ingest_raw_document, raw, session_id, state.store, state.embedder, settings
        )
    except EmptyDocumentError:
        raise HTTPException(422, "No readable text was found in that file.") from None
    except Exception as exc:
        log.warning("upload failed: %s, %d bytes, %s", suffix, len(data), type(exc).__name__)
        raise HTTPException(422, "That file could not be read.") from None
    log.info("upload stored: %s, %d bytes, %d passages", suffix, len(data), doc.n_chunks)
    return doc
