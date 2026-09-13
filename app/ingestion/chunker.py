"""Word-window chunking with overlap."""

import re

_WORD = re.compile(r"\S+")


def chunk_text(text: str, max_tokens: int, overlap_tokens: int) -> list[tuple[int, str]]:
    """Split ``text`` into overlapping windows of at most ``max_tokens`` words.

    Tokens are whitespace-separated words. Consecutive chunks share
    ``overlap_tokens`` words. Each chunk is a verbatim slice of ``text`` (inner
    whitespace, including line breaks, is preserved) so substring matches against
    the source text also match the chunk. Never returns an empty chunk: empty or
    whitespace-only input yields ``[]``. The last chunk may be shorter than
    ``max_tokens``.

    Returns ``[(chunk_index, chunk_text), ...]`` with indices starting at 0.
    """
    spans = [m.span() for m in _WORD.finditer(text)]
    if not spans:
        return []

    max_tokens = max(1, int(max_tokens))
    overlap = min(max(0, int(overlap_tokens)), max_tokens - 1)
    step = max_tokens - overlap

    chunks: list[tuple[int, str]] = []
    start = 0
    idx = 0
    while True:
        end = min(start + max_tokens, len(spans))
        chunks.append((idx, text[spans[start][0] : spans[end - 1][1]]))
        if end >= len(spans):
            break
        start += step
        idx += 1
    return chunks
