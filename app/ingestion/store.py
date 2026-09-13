"""SQLite store: documents, chunks, FTS5 keyword index, sqlite-vec vector index."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import sqlite_vec

from app.models import Chunk, DocumentInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    scope TEXT NOT NULL,
    n_chunks INTEGER NOT NULL,
    n_chars INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_scope ON documents(scope);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_doc ON chunks(doc_id, idx);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, content='chunks', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
    INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

_VEC_TABLE = (
    "CREATE VIRTUAL TABLE chunk_vec USING vec0("
    "chunk_id INTEGER PRIMARY KEY, embedding float[{dim}] distance_metric=cosine)"
)
_DIM_RE = re.compile(r"float\[(\d+)\]")
_FTS_TOKEN = re.compile(r"[^\W_]+")


class StoreDimensionError(ValueError):
    """The index on disk was built with a different embedding dimension."""


def _placeholders(n: int) -> str:
    return ",".join("?" * n)


def sanitize_fts_query(query: str) -> str:
    """Turn free text into a safe FTS5 expression: quoted tokens joined with OR."""
    tokens = _FTS_TOKEN.findall(query)
    return " OR ".join(f'"{t}"' for t in tokens if t)


class SqliteStore:
    """One SQLite file holding documents, chunks, the FTS5 index and the vec0 index."""

    def __init__(self, path: Path, dim: int) -> None:
        self.path = Path(path)
        self.dim = int(dim)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)
        self.conn.enable_load_extension(False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._ensure_schema()

    # -- schema -------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with self.conn:
            self.conn.executescript(_SCHEMA)
            row = self.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='chunk_vec'"
            ).fetchone()
            if row is None:
                self.conn.execute(_VEC_TABLE.format(dim=self.dim))
                return
        m = _DIM_RE.search(row["sql"] or "")
        stored = int(m.group(1)) if m else None
        if stored != self.dim:
            self.conn.close()
            raise StoreDimensionError(
                f"{self.path} was built with embedding dim {stored}, "
                f"but dim {self.dim} was requested"
            )

    # -- writes -------------------------------------------------------------

    def add_document(
        self, doc: DocumentInfo, chunks: list[str], vectors: list[list[float]]
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
        for i, v in enumerate(vectors):
            if len(v) != self.dim:
                raise StoreDimensionError(f"vector {i} has dim {len(v)}, store expects {self.dim}")
        with self.conn:
            self._delete_document_rows(doc.id)  # re-ingest replaces
            self.conn.execute(
                "INSERT INTO documents"
                "(id, title, source, scope, n_chunks, n_chars, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (
                    doc.id,
                    doc.title,
                    doc.source,
                    doc.scope,
                    len(chunks),
                    doc.n_chars,
                    doc.created_at,
                ),
            )
            cur = self.conn.cursor()
            for idx, (text, vec) in enumerate(zip(chunks, vectors)):
                cur.execute(
                    "INSERT INTO chunks(doc_id, idx, text) VALUES (?,?,?)", (doc.id, idx, text)
                )
                cur.execute(
                    "INSERT INTO chunk_vec(chunk_id, embedding) VALUES (?,?)",
                    (cur.lastrowid, sqlite_vec.serialize_float32(vec)),
                )

    def _delete_document_rows(self, doc_id: str) -> None:
        # Explicit deletes: vec0 has no triggers, and we do not rely on cascade order.
        self.conn.execute(
            "DELETE FROM chunk_vec WHERE chunk_id IN (SELECT id FROM chunks WHERE doc_id = ?)",
            (doc_id,),
        )
        self.conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        self.conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def delete_scope(self, scope: str) -> int:
        """Delete every document in ``scope`` from all tables; returns the document count."""
        with self.conn:
            ids = [
                r["id"]
                for r in self.conn.execute("SELECT id FROM documents WHERE scope = ?", (scope,))
            ]
            for doc_id in ids:
                self._delete_document_rows(doc_id)
        return len(ids)

    # -- searches -----------------------------------------------------------

    def keyword_search(self, query: str, scopes: list[str], k: int) -> list[tuple[int, float]]:
        """BM25 over FTS5, restricted to ``scopes``. Scores are positive; higher is better."""
        expr = sanitize_fts_query(query)
        if not expr or not scopes or k <= 0:
            return []
        rows = self.conn.execute(
            f"""
            SELECT c.id AS id, bm25(chunks_fts) AS s
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.doc_id
            WHERE chunks_fts MATCH ? AND d.scope IN ({_placeholders(len(scopes))})
            ORDER BY s ASC, c.id ASC
            LIMIT ?
            """,
            (expr, *scopes, k),
        ).fetchall()
        return [(r["id"], -float(r["s"])) for r in rows]

    def vector_search(
        self, vector: list[float], scopes: list[str], k: int
    ) -> list[tuple[int, float]]:
        """KNN over vec0 (cosine distance, lower is better), restricted to ``scopes``.

        Fetches ``k * 4`` neighbours, keeps those whose document is in scope, truncates
        to ``k``. If the scope filter leaves fewer than ``k`` the window widens (the
        preloaded corpus can crowd out a small upload) until the table is exhausted.
        """
        if len(vector) != self.dim:
            raise StoreDimensionError(
                f"query vector has dim {len(vector)}, store expects {self.dim}"
            )
        if not scopes or k <= 0:
            return []
        blob = sqlite_vec.serialize_float32(vector)
        total = self.conn.execute("SELECT COUNT(*) FROM chunk_vec").fetchone()[0]
        if total == 0:
            return []
        window = k * 4
        while True:
            window = min(window, total)
            # vec0 KNN must stand alone (no joins, one ORDER BY distance); filter after.
            rows = self.conn.execute(
                "SELECT chunk_id, distance FROM chunk_vec"
                " WHERE embedding MATCH ? AND k = ? ORDER BY distance",
                (blob, window),
            ).fetchall()
            allowed = self._ids_in_scopes([r["chunk_id"] for r in rows], scopes)
            kept = [(r["chunk_id"], float(r["distance"])) for r in rows if r["chunk_id"] in allowed]
            if len(kept) >= k or window >= total:
                break
            window *= 4
        return kept[:k]

    def _ids_in_scopes(self, ids: list[int], scopes: list[str], batch: int = 500) -> set[int]:
        allowed: set[int] = set()
        for i in range(0, len(ids), batch):
            part = ids[i : i + batch]
            rows = self.conn.execute(
                f"""
                SELECT c.id FROM chunks c JOIN documents d ON d.id = c.doc_id
                WHERE c.id IN ({_placeholders(len(part))})
                  AND d.scope IN ({_placeholders(len(scopes))})
                """,
                (*part, *scopes),
            ).fetchall()
            allowed.update(r["id"] for r in rows)
        return allowed

    # -- reads --------------------------------------------------------------

    def get_chunks(self, ids: list[int]) -> list[Chunk]:
        """Chunks for ``ids`` in the same order (unknown ids are skipped)."""
        if not ids:
            return []
        rows = self.conn.execute(
            f"""
            SELECT c.id, c.doc_id, d.title AS doc_title, c.idx, c.text
            FROM chunks c JOIN documents d ON d.id = c.doc_id
            WHERE c.id IN ({_placeholders(len(ids))})
            """,
            tuple(ids),
        ).fetchall()
        by_id = {r["id"]: Chunk(**dict(r)) for r in rows}
        seen: set[int] = set()
        out: list[Chunk] = []
        for i in ids:
            if i in by_id and i not in seen:
                out.append(by_id[i])
                seen.add(i)
        return out

    def neighbours(self, chunk_id: int) -> tuple[Chunk | None, Chunk | None]:
        row = self.conn.execute(
            "SELECT doc_id, idx FROM chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return (None, None)
        rows = self.conn.execute(
            """
            SELECT c.id, c.doc_id, d.title AS doc_title, c.idx, c.text
            FROM chunks c JOIN documents d ON d.id = c.doc_id
            WHERE c.doc_id = ? AND c.idx IN (?, ?)
            """,
            (row["doc_id"], row["idx"] - 1, row["idx"] + 1),
        ).fetchall()
        by_idx = {r["idx"]: Chunk(**dict(r)) for r in rows}
        return (by_idx.get(row["idx"] - 1), by_idx.get(row["idx"] + 1))

    def list_documents(self, scopes: list[str]) -> list[DocumentInfo]:
        if not scopes:
            return []
        rows = self.conn.execute(
            f"""
            SELECT id, title, source, scope, n_chunks, n_chars, created_at
            FROM documents WHERE scope IN ({_placeholders(len(scopes))})
            ORDER BY created_at ASC, rowid ASC
            """,
            tuple(scopes),
        ).fetchall()
        return [DocumentInfo(**dict(r)) for r in rows]

    def get_document(self, doc_id: str) -> DocumentInfo | None:
        row = self.conn.execute(
            "SELECT id, title, source, scope, n_chunks, n_chars, created_at"
            " FROM documents WHERE id = ?",
            (doc_id,),
        ).fetchone()
        return DocumentInfo(**dict(row)) if row else None

    def counts(self) -> dict:
        docs = self.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        return {"documents": int(docs), "chunks": int(chunks)}

    def close(self) -> None:
        self.conn.close()
