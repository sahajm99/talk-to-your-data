"""Build the preloaded index: ``python -m app.ingestion.preload``.

Reads every supported file in ``<data_dir>/preloaded``, deletes any existing index
at ``settings.index_path`` and ingests them under scope ``"preloaded"`` with stable
document ids (``sha1("preloaded" + file name)[:12]``).
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from typing import TextIO

from app.config import Settings, get_settings
from app.ingestion import loaders
from app.ingestion.embedder import get_embedder
from app.ingestion.pipeline import ingest_raw_document
from app.ingestion.store import SqliteStore
from app.models import DocumentInfo

SCOPE = "preloaded"
SUPPORTED = {".txt", ".md", ".pdf", ".docx"}
TITLES = {
    "sherlock-holmes.txt": "The Adventures of Sherlock Holmes",
    "federalist-papers.txt": "The Federalist Papers",
    "nist-sp-800-63-3.pdf": "NIST SP 800-63-3 Digital Identity Guidelines",
}


def preloaded_doc_id(file_name: str) -> str:
    return hashlib.sha1(f"{SCOPE}{file_name}".encode()).hexdigest()[:12]


def preloaded_files(data_dir: Path) -> list[Path]:
    folder = data_dir / "preloaded"
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED)


def remove_index(index_path: Path) -> None:
    for suffix in ("", "-wal", "-shm", "-journal"):
        p = index_path.with_name(index_path.name + suffix)
        if p.exists():
            p.unlink()


def build(
    settings: Settings | None = None, out: TextIO = sys.stdout
) -> list[tuple[DocumentInfo, float]]:
    settings = settings or get_settings()
    files = preloaded_files(settings.data_dir)
    if not files:
        raise SystemExit(f"no documents found in {settings.data_dir / 'preloaded'}")

    remove_index(settings.index_path)
    embedder = get_embedder(settings)
    store = SqliteStore(settings.index_path, embedder.dim)
    results: list[tuple[DocumentInfo, float]] = []
    total_start = time.perf_counter()
    try:
        for path in files:
            t0 = time.perf_counter()
            raw = loaders.from_path(SCOPE, path)
            doc = ingest_raw_document(
                raw,
                SCOPE,
                store,
                embedder,
                settings,
                doc_id=preloaded_doc_id(path.name),
                title=TITLES.get(path.name),
            )
            results.append((doc, time.perf_counter() - t0))
        counts = store.counts()
    finally:
        store.close()
    total = time.perf_counter() - total_start

    print(f"embed model: {settings.embed_model}  dim: {embedder.dim}", file=out)
    print(f"index: {settings.index_path}", file=out)
    header = ("title", "id", "chunks", "chars", "seconds")
    print(
        f"{header[0]:<46} {header[1]:<12} {header[2]:>7} {header[3]:>10} {header[4]:>8}", file=out
    )
    for doc, secs in results:
        print(
            f"{doc.title[:46]:<46} {doc.id:<12} {doc.n_chunks:>7} {doc.n_chars:>10,} {secs:>8.1f}",
            file=out,
        )
    total_chars = sum(d.n_chars for d, _ in results)
    print(
        f"{'total':<46} {'':<12} {counts['chunks']:>7} {total_chars:>10,} {total:>8.1f}",
        file=out,
    )
    return results


if __name__ == "__main__":
    build()
