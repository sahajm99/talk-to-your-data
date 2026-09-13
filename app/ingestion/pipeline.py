"""Ingestion: RawDocument -> text -> chunks -> vectors -> store."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import PurePath

from app.config import Settings, get_settings
from app.ingestion.chunker import chunk_text
from app.ingestion.embedder import Embedder
from app.ingestion.loaders import RawDocument
from app.ingestion.store import SqliteStore
from app.ingestion.text_extractors import extract_text
from app.models import DocumentInfo

GUTENBERG_START = "*** START OF"
GUTENBERG_END = "*** END OF"


class EmptyDocumentError(ValueError):
    """No text could be extracted from the document."""


def strip_gutenberg(text: str) -> str:
    """Drop the Project Gutenberg header and licence when the marker lines are present.

    Keeps everything after the line starting with ``*** START OF`` and before the
    line starting with ``*** END OF``. Text without markers is returned unchanged.
    """
    lines = text.split("\n")
    start = 0
    end = len(lines)
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(GUTENBERG_START) and start == 0:
            start = i + 1
        elif s.startswith(GUTENBERG_END):
            end = i
            break
    if start == 0 and end == len(lines):
        return text
    return "\n".join(lines[start:end]).strip()


def clean_title(file_name: str) -> str:
    """``my_resume-v2.pdf`` -> ``My Resume V2``; words that are not all lower-case are kept."""
    stem = PurePath(file_name).stem
    words = re.sub(r"[-_.\s]+", " ", stem).strip().split()
    if not words:
        return file_name or "Untitled"
    return " ".join(w.capitalize() if w.islower() else w for w in words)


def document_id(scope: str, title: str, n_chars: int) -> str:
    return hashlib.sha1(f"{scope}{title}{n_chars}".encode()).hexdigest()[:12]


def ingest_raw_document(
    raw: RawDocument,
    scope: str,
    store: SqliteStore,
    embedder: Embedder,
    settings: Settings | None = None,
    *,
    doc_id: str | None = None,
    title: str | None = None,
) -> DocumentInfo:
    """Extract, chunk, embed and store one document under ``scope``.

    ``doc_id`` defaults to ``sha1(scope + title + n_chars)[:12]``; ``title`` to the
    cleaned file stem. Both can be pinned (preload does, so its ids are stable).
    Raises ``EmptyDocumentError`` when nothing chunkable was extracted.
    """
    settings = settings or get_settings()
    text, _meta = extract_text(raw)
    text = strip_gutenberg(text)
    pieces = chunk_text(text, settings.chunk_max_tokens, settings.chunk_overlap_tokens)
    if not pieces:
        raise EmptyDocumentError(f"no text could be extracted from {raw.file_name!r}")

    title = title or clean_title(raw.file_name)
    n_chars = len(text)
    doc = DocumentInfo(
        id=doc_id or document_id(scope, title, n_chars),
        title=title,
        source=raw.file_name,
        scope=scope,
        n_chunks=len(pieces),
        n_chars=n_chars,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    texts = [body for _, body in pieces]
    vectors = embedder.embed(texts)
    store.add_document(doc, texts, vectors)
    return doc
