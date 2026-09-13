"""SqliteStore round trip with the FakeEmbedder."""

import pytest

from app.ingestion.embedder import FakeEmbedder
from app.ingestion.store import SqliteStore, StoreDimensionError, sanitize_fts_query
from tests.conftest import make_doc

A_CHUNKS = [
    "Sherlock Holmes lived at Baker Street with Doctor Watson.",
    "The detective solved the mystery of the speckled band.",
]
B_CHUNKS = [
    "Hamilton argued for a strong federal constitution in the essays.",
    "The speckled band was a swamp adder, said Holmes.",
]


@pytest.fixture
def two_scope_store(store: SqliteStore, embedder: FakeEmbedder) -> SqliteStore:
    store.add_document(
        make_doc("doc-a", "preloaded", n_chunks=2), A_CHUNKS, embedder.embed(A_CHUNKS)
    )
    store.add_document(
        make_doc("doc-b", "session-1", n_chunks=2), B_CHUNKS, embedder.embed(B_CHUNKS)
    )
    return store


def _table_count(store: SqliteStore, table: str) -> int:
    return store.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_counts_and_wal(two_scope_store: SqliteStore):
    assert two_scope_store.counts() == {"documents": 2, "chunks": 4}
    assert two_scope_store.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert _table_count(two_scope_store, "chunk_vec") == 4
    assert _table_count(two_scope_store, "chunks_fts") == 4


def test_keyword_search_finds_the_right_chunk(two_scope_store: SqliteStore):
    hits = two_scope_store.keyword_search("Hamilton constitution", ["preloaded", "session-1"], 5)
    assert len(hits) == 1
    chunk_id, score = hits[0]
    assert score > 0
    [chunk] = two_scope_store.get_chunks([chunk_id])
    assert chunk.doc_id == "doc-b"
    assert chunk.idx == 0
    assert chunk.doc_title == "Doc-B"


def test_keyword_search_ranks_best_match_first(two_scope_store: SqliteStore):
    hits = two_scope_store.keyword_search("speckled band adder", ["preloaded", "session-1"], 5)
    ids = [cid for cid, _ in hits]
    chunks = {c.id: c for c in two_scope_store.get_chunks(ids)}
    assert len(hits) == 2
    assert chunks[ids[0]].text.startswith("The speckled band was a swamp adder")
    scores = [s for _, s in hits]
    assert scores == sorted(scores, reverse=True)


def test_keyword_search_scope_filter(two_scope_store: SqliteStore):
    assert two_scope_store.keyword_search("Hamilton", ["preloaded"], 5) == []
    hits = two_scope_store.keyword_search("Holmes", ["session-1"], 5)
    [chunk] = two_scope_store.get_chunks([hits[0][0]])
    assert chunk.doc_id == "doc-b"
    assert two_scope_store.keyword_search("Holmes", [], 5) == []


def test_keyword_search_survives_operators_and_punctuation(two_scope_store: SqliteStore):
    hits = two_scope_store.keyword_search(
        'Holmes AND "Watson" NOT (band) OR * : ^ -', ["preloaded", "session-1"], 5
    )
    assert hits, "query with FTS5 syntax characters should still match"
    assert two_scope_store.keyword_search("??? !!!", ["preloaded"], 5) == []


def test_sanitize_fts_query():
    assert sanitize_fts_query("Baker Street, 221B!") == '"Baker" OR "Street" OR "221B"'
    assert sanitize_fts_query("") == ""
    assert sanitize_fts_query("a-b_c") == '"a" OR "b" OR "c"'


def test_vector_search_returns_doc_sharing_words(
    two_scope_store: SqliteStore, embedder: FakeEmbedder
):
    q = embedder.embed_query("Sherlock Holmes lived at Baker Street with Doctor Watson")
    hits = two_scope_store.vector_search(q, ["preloaded", "session-1"], 2)
    assert len(hits) == 2
    [best] = two_scope_store.get_chunks([hits[0][0]])
    assert best.doc_id == "doc-a" and best.idx == 0
    assert hits[0][1] < hits[1][1]  # cosine distance ascending
    assert hits[0][1] == pytest.approx(0.0, abs=1e-5)


def test_vector_search_scope_filter(two_scope_store: SqliteStore, embedder: FakeEmbedder):
    q = embedder.embed_query("Sherlock Holmes lived at Baker Street with Doctor Watson")
    hits = two_scope_store.vector_search(q, ["session-1"], 5)
    chunks = two_scope_store.get_chunks([cid for cid, _ in hits])
    assert chunks and all(c.doc_id == "doc-b" for c in chunks)
    assert two_scope_store.vector_search(q, ["nope"], 5) == []
    assert two_scope_store.vector_search(q, [], 5) == []


def test_vector_search_widens_when_scope_is_crowded_out(store: SqliteStore, embedder: FakeEmbedder):
    filler = [f"filler passage number {i} about weather and clouds" for i in range(60)]
    store.add_document(make_doc("big", "preloaded", n_chunks=60), filler, embedder.embed(filler))
    small = ["a lonely note about gardening tomatoes"]
    store.add_document(make_doc("small", "session-9", n_chunks=1), small, embedder.embed(small))
    q = embedder.embed_query("filler passage number about weather and clouds")
    hits = store.vector_search(q, ["session-9"], 1)
    [chunk] = store.get_chunks([hits[0][0]])
    assert chunk.doc_id == "small"


def test_vector_query_dim_mismatch_raises(two_scope_store: SqliteStore):
    with pytest.raises(StoreDimensionError):
        two_scope_store.vector_search([0.0] * 3, ["preloaded"], 5)


def test_get_chunks_preserves_order_and_skips_unknown(two_scope_store: SqliteStore):
    ids = [c.id for c in two_scope_store.get_chunks([1, 2, 3, 4])]
    assert ids == [1, 2, 3, 4]
    reordered = two_scope_store.get_chunks([4, 1, 999, 3, 1])
    assert [c.id for c in reordered] == [4, 1, 3]
    assert two_scope_store.get_chunks([]) == []


def test_neighbours(two_scope_store: SqliteStore):
    first = two_scope_store.get_chunks([1])[0]
    prev, nxt = two_scope_store.neighbours(first.id)
    assert prev is None
    assert nxt is not None and nxt.doc_id == first.doc_id and nxt.idx == 1
    prev2, nxt2 = two_scope_store.neighbours(nxt.id)
    assert prev2 is not None and prev2.id == first.id
    assert nxt2 is None  # last chunk of doc-a; doc-b is not a neighbour
    assert two_scope_store.neighbours(12345) == (None, None)


def test_list_documents(two_scope_store: SqliteStore):
    docs = two_scope_store.list_documents(["preloaded", "session-1"])
    assert [d.id for d in docs] == ["doc-a", "doc-b"]
    assert docs[0].n_chunks == 2 and docs[0].scope == "preloaded"
    assert [d.id for d in two_scope_store.list_documents(["session-1"])] == ["doc-b"]
    assert two_scope_store.list_documents([]) == []
    assert two_scope_store.get_document("doc-b").scope == "session-1"
    assert two_scope_store.get_document("missing") is None


def test_delete_scope_removes_rows_in_every_table(two_scope_store: SqliteStore):
    assert two_scope_store.delete_scope("session-1") == 1
    assert two_scope_store.delete_scope("session-1") == 0
    assert two_scope_store.counts() == {"documents": 1, "chunks": 2}
    assert _table_count(two_scope_store, "chunk_vec") == 2
    assert _table_count(two_scope_store, "chunks_fts") == 2
    assert two_scope_store.keyword_search("Hamilton", ["preloaded", "session-1"], 5) == []
    remaining = two_scope_store.list_documents(["preloaded", "session-1"])
    assert [d.id for d in remaining] == ["doc-a"]


def test_re_adding_a_document_replaces_it(two_scope_store: SqliteStore, embedder: FakeEmbedder):
    new_chunks = ["Entirely new text about lighthouses."]
    two_scope_store.add_document(
        make_doc("doc-a", "preloaded", n_chunks=1), new_chunks, embedder.embed(new_chunks)
    )
    assert two_scope_store.counts() == {"documents": 2, "chunks": 3}
    assert _table_count(two_scope_store, "chunk_vec") == 3
    assert two_scope_store.keyword_search("Watson", ["preloaded"], 5) == []
    assert two_scope_store.keyword_search("lighthouses", ["preloaded"], 5)


def test_add_document_validates_vectors(store: SqliteStore, embedder: FakeEmbedder):
    with pytest.raises(StoreDimensionError):
        store.add_document(make_doc("x", "s"), ["one chunk"], [[0.0] * 5])
    with pytest.raises(ValueError):
        store.add_document(make_doc("x", "s"), ["one", "two"], embedder.embed(["one"]))
    assert store.counts() == {"documents": 0, "chunks": 0}


def test_dim_mismatch_on_reopen_raises(tmp_path, embedder: FakeEmbedder):
    path = tmp_path / "dim.db"
    s = SqliteStore(path, embedder.dim)
    s.add_document(make_doc("d", "s", n_chunks=1), ["hello world"], embedder.embed(["hello world"]))
    s.close()
    with pytest.raises(StoreDimensionError):
        SqliteStore(path, 384)
    reopened = SqliteStore(path, embedder.dim)  # same dim reopens fine, data intact
    assert reopened.counts() == {"documents": 1, "chunks": 1}
    reopened.close()
