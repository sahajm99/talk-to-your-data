"""RRF and hybrid_search over the three-document fixture."""

import pytest

from app.ingestion.embedder import FakeEmbedder
from app.ingestion.retrieval import Hit, hybrid_search, rrf
from app.ingestion.store import SqliteStore
from app.models import Chunk

ALL = ["preloaded", "session-1"]


def test_rrf_hand_case():
    result = rrf([[1, 2, 3], [3, 1]])
    assert [id_ for id_, _ in result] == [1, 3, 2]
    scores = dict(result)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62, abs=1e-9)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61, abs=1e-9)
    assert scores[2] == pytest.approx(1 / 62, abs=1e-9)


def test_rrf_ties_keep_first_appearance():
    assert [id_ for id_, _ in rrf([[1], [2]])] == [1, 2]
    assert [id_ for id_, _ in rrf([[2], [1]])] == [2, 1]
    assert rrf([[7]], k=10) == [(7, pytest.approx(1 / 11))]


def test_rrf_empty():
    assert rrf([]) == []
    assert rrf([[], []]) == []


def _titles(hits: list[Hit]) -> list[str]:
    return [h.chunk.doc_id for h in hits]


def test_keyword_mode(three_doc_store: SqliteStore, embedder: FakeEmbedder):
    hits = hybrid_search(three_doc_store, embedder, "Baker Street", ALL, k=3, mode="keyword")
    assert hits and hits[0].chunk.doc_id == "holmes" and hits[0].chunk.idx == 0
    for rank, h in enumerate(hits, start=1):
        assert h.via == ["keyword"]
        assert h.keyword_rank == rank
        assert h.vector_rank is None
        assert h.score > 0


def test_vector_mode(three_doc_store: SqliteStore, embedder: FakeEmbedder):
    q = "Sherlock Holmes lived at 221B Baker Street with Doctor Watson"
    hits = hybrid_search(three_doc_store, embedder, q, ALL, k=3, mode="vector")
    assert len(hits) == 3
    assert hits[0].chunk.doc_id == "holmes" and hits[0].chunk.idx == 0
    assert hits[0].score == pytest.approx(1.0, abs=1e-5)  # cosine similarity
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    for rank, h in enumerate(hits, start=1):
        assert h.via == ["vector"]
        assert h.vector_rank == rank
        assert h.keyword_rank is None


def test_hybrid_mode_fuses_both_lists(three_doc_store: SqliteStore, embedder: FakeEmbedder):
    q = "fox jumps over the lazy dog"
    kw = three_doc_store.keyword_search(q, ALL, 20)
    vec = three_doc_store.vector_search(embedder.embed_query(q), ALL, 20)
    expected = rrf([[i for i, _ in kw], [i for i, _ in vec]])[:5]

    hits = hybrid_search(three_doc_store, embedder, q, ALL, k=5, candidates=20, mode="hybrid")
    assert [h.chunk.id for h in hits] == [i for i, _ in expected]
    assert [h.score for h in hits] == pytest.approx([s for _, s in expected])
    assert hits[0].chunk.doc_id == "fox" and hits[0].chunk.idx == 0

    kw_ids = {i for i, _ in kw}
    vec_ids = {i for i, _ in vec}
    for h in hits:
        assert h.via == [
            n for n, ids in (("keyword", kw_ids), ("vector", vec_ids)) if h.chunk.id in ids
        ]
        assert (h.keyword_rank is not None) == (h.chunk.id in kw_ids)
        assert (h.vector_rank is not None) == (h.chunk.id in vec_ids)
    assert hits[0].via == ["keyword", "vector"]


def test_hybrid_respects_k_and_scopes(three_doc_store: SqliteStore, embedder: FakeEmbedder):
    hits = hybrid_search(three_doc_store, embedder, "the constitution essays", ALL, k=2)
    assert len(hits) == 2
    only_session = hybrid_search(
        three_doc_store, embedder, "Sherlock Holmes Baker Street", ["session-1"], k=5
    )
    assert only_session and all(h.chunk.doc_id == "federalist" for h in only_session)
    assert hybrid_search(three_doc_store, embedder, "anything", [], k=5) == []
    assert hybrid_search(three_doc_store, embedder, "anything", ALL, k=0) == []


def test_keyword_mode_with_no_matching_terms_is_empty(three_doc_store, embedder):
    assert hybrid_search(three_doc_store, embedder, "zzzz qqqq", ALL, mode="keyword") == []
    # hybrid still answers through the vector list
    assert hybrid_search(three_doc_store, embedder, "zzzz qqqq", ALL, mode="hybrid")


def test_invalid_mode(three_doc_store: SqliteStore, embedder: FakeEmbedder):
    with pytest.raises(ValueError):
        hybrid_search(three_doc_store, embedder, "x", ALL, mode="semantic")


def test_hit_to_retrieval_hit_preview():
    chunk = Chunk(id=9, doc_id="d", doc_title="Doc", idx=2, text="x" * 500)
    hit = Hit(chunk=chunk, score=0.5, via=["keyword", "vector"], keyword_rank=1, vector_rank=3)
    rh = hit.to_retrieval_hit()
    assert rh.chunk_id == 9 and rh.doc_title == "Doc" and rh.idx == 2
    assert len(rh.preview) == 240
    assert rh.via == ["keyword", "vector"] and rh.keyword_rank == 1 and rh.vector_rank == 3
