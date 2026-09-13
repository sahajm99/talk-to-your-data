"""Ingestion pipeline and preload with the FakeEmbedder."""

import io
import re
from pathlib import Path

import pytest
from starlette.datastructures import Headers, UploadFile

from app.config import Settings
from app.ingestion import loaders, preload
from app.ingestion.embedder import FakeEmbedder
from app.ingestion.file_types import FileType
from app.ingestion.loaders import RawDocument
from app.ingestion.pipeline import (
    EmptyDocumentError,
    clean_title,
    document_id,
    ingest_raw_document,
    strip_gutenberg,
)
from app.ingestion.store import SqliteStore

BODY = " ".join(f"word{i}" for i in range(120))
GUTENBERG = (
    "The Project Gutenberg eBook of A Small Book\n\n"
    "This eBook is for the use of anyone anywhere.\n"
    "Title: A Small Book\n\n"
    "*** START OF THE PROJECT GUTENBERG EBOOK A SMALL BOOK ***\n\n"
    "CHAPTER I\n\n" + BODY + "\n\n"
    "*** END OF THE PROJECT GUTENBERG EBOOK A SMALL BOOK ***\n\n"
    "Section 1. General Terms of Use and Redistributing.\n"
)


def _raw(name: str, content: bytes, file_type: FileType = FileType.TXT) -> RawDocument:
    return RawDocument(
        project_id="s",
        source_id=Path(name).stem,
        file_type=file_type,
        file_name=name,
        bytes=content,
    )


def test_strip_gutenberg():
    body = strip_gutenberg(GUTENBERG)
    assert body.startswith("CHAPTER I")
    assert body.endswith("word119")
    assert "Project Gutenberg" not in body
    assert "General Terms" not in body
    plain = "no markers here\njust text"
    assert strip_gutenberg(plain) == plain


def test_clean_title():
    assert clean_title("sherlock-holmes.txt") == "Sherlock Holmes"
    assert clean_title("my_resume  v2.final.pdf") == "My Resume V2 Final"
    assert clean_title("NIST-SP-800-63-3.pdf") == "NIST SP 800 63 3"
    assert clean_title("weird___.md") == "Weird"


def test_document_id_is_stable_and_scope_dependent():
    assert re.fullmatch(r"[0-9a-f]{12}", document_id("preloaded", "T", 10))
    assert document_id("preloaded", "T", 10) == document_id("preloaded", "T", 10)
    assert document_id("preloaded", "T", 10) != document_id("session", "T", 10)
    assert document_id("preloaded", "T", 10) != document_id("preloaded", "T", 11)


def test_ingest_txt_strips_gutenberg_and_stores(
    store: SqliteStore, embedder: FakeEmbedder, settings: Settings
):
    raw = _raw("a-small_book.txt", GUTENBERG.encode("utf-8"))
    doc = ingest_raw_document(raw, "session-1", store, embedder, settings)

    assert doc.title == "A Small Book"
    assert doc.source == "a-small_book.txt"
    assert doc.scope == "session-1"
    assert re.fullmatch(r"[0-9a-f]{12}", doc.id)
    assert doc.id == document_id("session-1", "A Small Book", doc.n_chars)
    assert doc.n_chars == len(strip_gutenberg(GUTENBERG))
    # 122 words, windows of 40 with overlap 10 -> starts at 0, 30, 60, 90
    assert doc.n_chunks == 4
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", doc.created_at)

    assert store.counts() == {"documents": 1, "chunks": 4}
    assert store.list_documents(["session-1"])[0] == doc
    chunks = store.get_chunks([1, 2, 3, 4])
    assert chunks[0].text.startswith("CHAPTER I")
    assert chunks[-1].text.endswith("word119")
    assert all("Gutenberg" not in c.text for c in chunks)
    assert store.keyword_search("Gutenberg", ["session-1"], 5) == []
    hits = store.keyword_search("word119", ["session-1"], 5)
    assert [store.get_chunks([h[0]])[0].idx for h in hits] == [3]


def test_ingest_empty_document_raises(store, embedder, settings):
    with pytest.raises(EmptyDocumentError):
        ingest_raw_document(_raw("blank.txt", b"   \n  "), "s", store, embedder, settings)
    assert store.counts() == {"documents": 0, "chunks": 0}


def test_ingest_pins_id_and_title(store, embedder, settings):
    raw = _raw("x.txt", b"some words here")
    doc = ingest_raw_document(
        raw, "s", store, embedder, settings, doc_id="abc123abc123", title="Pinned"
    )
    assert doc.id == "abc123abc123" and doc.title == "Pinned"


def test_ingest_uses_get_settings_when_none_given(store, embedder, monkeypatch):
    monkeypatch.setenv("CHUNK_MAX_TOKENS", "5")
    monkeypatch.setenv("CHUNK_OVERLAP_TOKENS", "1")
    from app.config import get_settings

    get_settings.cache_clear()
    try:
        doc = ingest_raw_document(
            _raw("t.txt", b"one two three four five six seven"), "s", store, embedder
        )
        assert doc.n_chunks == 2
    finally:
        get_settings.cache_clear()


async def test_ingest_from_upload_file(store, embedder, settings):
    upload = UploadFile(
        io.BytesIO(b"notes about lighthouses and their keepers"),
        filename="lighthouse notes.md",
        headers=Headers({"content-type": "text/markdown"}),
    )
    raw = await loaders.from_upload_file("session-2", upload)
    assert raw.file_type == FileType.MARKDOWN
    doc = ingest_raw_document(raw, "session-2", store, embedder, settings)
    assert doc.title == "Lighthouse Notes"
    assert store.keyword_search("lighthouses", ["session-2"], 5)


def test_ingest_from_path(tmp_path, store, embedder, settings):
    p = tmp_path / "from-disk.txt"
    p.write_text("text read from a file on disk", encoding="utf-8")
    raw = loaders.from_path("s", p)
    doc = ingest_raw_document(raw, "s", store, embedder, settings)
    assert doc.title == "From Disk" and doc.n_chunks == 1


def test_preload_builds_index_with_stable_ids(settings: Settings):
    folder = settings.data_dir / "preloaded"
    folder.mkdir(parents=True)
    (folder / "sherlock-holmes.txt").write_text(GUTENBERG, encoding="utf-8")
    (folder / "zebra-facts.txt").write_text("Zebras have stripes. " * 30, encoding="utf-8")
    (folder / "ignored.json").write_text("{}", encoding="utf-8")

    out = io.StringIO()
    results = preload.build(settings, out=out)
    assert [d.source for d, _ in results] == ["sherlock-holmes.txt", "zebra-facts.txt"]
    assert results[0][0].title == "The Adventures of Sherlock Holmes"  # TITLES override
    assert results[1][0].title == "Zebra Facts"
    for doc, secs in results:
        assert doc.scope == "preloaded"
        assert doc.id == preload.preloaded_doc_id(doc.source)
        assert secs >= 0
    assert preload.preloaded_doc_id("sherlock-holmes.txt") == results[0][0].id
    table = out.getvalue()
    assert "The Adventures of Sherlock Holmes" in table and "chunks" in table and "seconds" in table

    s = SqliteStore(settings.index_path, FakeEmbedder.dim)
    try:
        assert s.counts()["documents"] == 2
        assert [d.id for d in s.list_documents(["preloaded"])] == [d.id for d, _ in results]
    finally:
        s.close()

    # a second build starts from an empty file rather than appending
    preload.build(settings, out=io.StringIO())
    s = SqliteStore(settings.index_path, FakeEmbedder.dim)
    try:
        assert s.counts()["documents"] == 2
    finally:
        s.close()


def test_preload_with_no_files_exits(settings: Settings):
    with pytest.raises(SystemExit):
        preload.build(settings, out=io.StringIO())
