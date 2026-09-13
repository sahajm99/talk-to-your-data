"""Tests for word-window chunking."""

from app.ingestion.chunker import chunk_text


def test_small_text_is_one_chunk():
    text = "This is a small text that should fit in one chunk."
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    assert chunks == [(0, text)]


def test_respects_max_tokens_and_indices():
    text = " ".join(f"w{i}" for i in range(500))
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    assert [idx for idx, _ in chunks] == list(range(len(chunks)))
    for _, body in chunks:
        assert 0 < len(body.split()) <= 100
    # every word is covered, and the final word ends the last chunk
    assert chunks[0][1].split()[0] == "w0"
    assert chunks[-1][1].split()[-1] == "w499"


def test_overlap_between_consecutive_chunks():
    text = " ".join(f"w{i}" for i in range(200))
    chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
    assert len(chunks) == 5  # starts at 0, 40, 80, 120, 160
    first, second = chunks[0][1].split(), chunks[1][1].split()
    assert first[-10:] == second[:10]
    assert second[0] == "w40"


def test_last_chunk_may_be_short_but_never_empty():
    text = " ".join(f"w{i}" for i in range(105))
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=50)
    assert len(chunks) == 2
    assert chunks[1][1].split()[0] == "w50"
    assert chunks[1][1].split()[-1] == "w104"
    assert all(body.strip() for _, body in chunks)


def test_exact_multiple_does_not_produce_empty_tail():
    text = " ".join(["word"] * 100)
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    assert len(chunks) == 1


def test_empty_and_whitespace_text_yield_no_chunks():
    assert chunk_text("", max_tokens=100, overlap_tokens=10) == []
    assert chunk_text("   \n\t ", max_tokens=100, overlap_tokens=10) == []


def test_preserves_inner_whitespace_and_newlines():
    text = "one two\nthree   four\n\nfive"
    chunks = chunk_text(text, max_tokens=3, overlap_tokens=1)
    assert chunks[0][1] == "one two\nthree"
    assert chunks[1][1] == "three   four\n\nfive"


def test_overlap_larger_than_window_still_terminates():
    text = " ".join(f"w{i}" for i in range(30))
    chunks = chunk_text(text, max_tokens=10, overlap_tokens=50)
    assert chunks[-1][1].split()[-1] == "w29"
    assert len(chunks) == 21  # step clamps to 1
