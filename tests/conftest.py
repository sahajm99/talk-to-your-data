"""Shared fixtures: FakeEmbedder, temp-file stores, small chunk settings."""

from pathlib import Path

import pytest

from app.config import Settings
from app.ingestion.embedder import FakeEmbedder
from app.ingestion.store import SqliteStore
from app.models import DocumentInfo


def make_doc(
    doc_id: str,
    scope: str,
    title: str | None = None,
    n_chunks: int = 0,
    n_chars: int = 0,
) -> DocumentInfo:
    return DocumentInfo(
        id=doc_id,
        title=title or doc_id.title(),
        source=f"{doc_id}.txt",
        scope=scope,
        n_chunks=n_chunks,
        n_chars=n_chars,
        created_at="2026-09-12T00:00:00+00:00",
    )


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        embed_model="fake",
        data_dir=tmp_path / "data",
        index_path=tmp_path / "data" / "index.db",
        chunk_max_tokens=40,
        chunk_overlap_tokens=10,
    )


@pytest.fixture
def store(tmp_path: Path, embedder: FakeEmbedder):
    s = SqliteStore(tmp_path / "index.db", embedder.dim)
    yield s
    s.close()


THREE_DOCS: list[tuple[str, str, list[str]]] = [
    (
        "fox",
        "preloaded",
        [
            "The quick brown fox jumps over the lazy dog near the river.",
            "A fox is a small omnivorous mammal with a bushy tail.",
        ],
    ),
    (
        "holmes",
        "preloaded",
        [
            "Sherlock Holmes lived at 221B Baker Street with Doctor Watson.",
            "Watson wrote about the cases of the consulting detective.",
        ],
    ),
    (
        "federalist",
        "session-1",
        [
            "The Federalist Papers argue for ratification of the constitution.",
            "Hamilton Madison and Jay wrote the essays under the name Publius.",
        ],
    ),
]


@pytest.fixture
def three_doc_store(store: SqliteStore, embedder: FakeEmbedder) -> SqliteStore:
    for doc_id, scope, chunks in THREE_DOCS:
        doc = make_doc(doc_id, scope, n_chunks=len(chunks), n_chars=sum(map(len, chunks)))
        store.add_document(doc, chunks, embedder.embed(chunks))
    return store
