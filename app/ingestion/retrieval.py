"""Keyword, vector and hybrid (RRF) retrieval over a SqliteStore."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.ingestion.embedder import Embedder
from app.ingestion.store import SqliteStore
from app.models import Chunk, RetrievalHit

MODES = ("keyword", "vector", "hybrid")
PREVIEW_CHARS = 240


def rrf(rankings: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal rank fusion: score(id) = sum over lists of 1 / (k + rank), rank from 1.

    Sorted by score descending; ties keep the order of first appearance.
    """
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, id_ in enumerate(ranking, start=1):
            scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank)
    # dict preserves first appearance; sorted() is stable, so ties keep that order
    return sorted(scores.items(), key=lambda item: -item[1])


@dataclass
class Hit:
    chunk: Chunk
    score: float
    via: list[str] = field(default_factory=list)
    keyword_rank: int | None = None
    vector_rank: int | None = None

    def to_retrieval_hit(self) -> RetrievalHit:
        return RetrievalHit(
            chunk_id=self.chunk.id,
            doc_title=self.chunk.doc_title,
            idx=self.chunk.idx,
            score=self.score,
            via=list(self.via),
            keyword_rank=self.keyword_rank,
            vector_rank=self.vector_rank,
            preview=self.chunk.text[:PREVIEW_CHARS],
        )


def hybrid_search(
    store: SqliteStore,
    embedder: Embedder,
    query: str,
    scopes: list[str],
    k: int = 5,
    candidates: int = 20,
    mode: str = "hybrid",
) -> list[Hit]:
    """Top-``k`` chunks for ``query`` within ``scopes``.

    ``mode`` is ``"keyword"`` (score = BM25), ``"vector"`` (score = cosine similarity,
    ``1 - distance``) or ``"hybrid"`` (score = RRF over both candidate lists).
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
    if k <= 0 or not scopes:
        return []
    candidates = max(candidates, k)

    kw: list[tuple[int, float]] = []
    vec: list[tuple[int, float]] = []
    if mode in ("keyword", "hybrid"):
        kw = store.keyword_search(query, scopes, candidates)
    if mode in ("vector", "hybrid"):
        vec = store.vector_search(embedder.embed_query(query), scopes, candidates)

    kw_rank = {id_: r for r, (id_, _) in enumerate(kw, start=1)}
    vec_rank = {id_: r for r, (id_, _) in enumerate(vec, start=1)}

    if mode == "keyword":
        ranked = kw[:k]
    elif mode == "vector":
        ranked = [(id_, 1.0 - dist) for id_, dist in vec[:k]]
    else:
        ranked = rrf([[id_ for id_, _ in kw], [id_ for id_, _ in vec]])[:k]

    chunks = {c.id: c for c in store.get_chunks([id_ for id_, _ in ranked])}
    hits: list[Hit] = []
    for id_, score in ranked:
        chunk = chunks.get(id_)
        if chunk is None:
            continue
        via = [name for name, ranks in (("keyword", kw_rank), ("vector", vec_rank)) if id_ in ranks]
        hits.append(
            Hit(
                chunk=chunk,
                score=float(score),
                via=via,
                keyword_rank=kw_rank.get(id_),
                vector_rank=vec_rank.get(id_),
            )
        )
    return hits
