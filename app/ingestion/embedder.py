"""Embedding backends: fastembed in production, a deterministic fake for tests."""

from __future__ import annotations

import hashlib
import math
import re
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.config import Settings

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:  # documents
        ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedder:
    """`fastembed` TextEmbedding, loaded on first use.

    bge-small-en-v1.5 needs no query prefix; fastembed's ``query_embed`` applies a
    prefix only for models that require one, so queries go through it unchanged.
    """

    dim = 384

    def __init__(self, model_name: str = DEFAULT_MODEL, batch_size: int = 64) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self._model: Any = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding  # imported lazily: slow and optional in tests

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [v.tolist() for v in self.model.embed(texts, batch_size=self.batch_size)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self.model.query_embed(text))).tolist()


_TOKEN = re.compile(r"[^\W_]+")


class FakeEmbedder:
    """Deterministic hashed bag-of-words unit vectors (dim 16).

    Each word is hashed (sha1, so it is stable across processes) to a bucket and a
    sign; the counts are L2-normalised. Texts that share words land closer in cosine
    space, which is all the tests and the ``EMBED_MODEL=fake`` mode need.
    """

    dim = 16

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        for word in _TOKEN.findall(text.lower()):
            h = hashlib.sha1(word.encode("utf-8")).digest()
            bucket = h[0] % self.dim
            sign = 1.0 if h[1] % 2 == 0 else -1.0
            v[bucket] += sign
        norm = math.sqrt(sum(x * x for x in v))
        if norm == 0.0:
            v[0] = 1.0
            return v
        return [x / norm for x in v]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def get_embedder(settings: Settings) -> Embedder:
    """``EMBED_MODEL=fake`` selects the FakeEmbedder; anything else is a fastembed model name."""
    name = (settings.embed_model or DEFAULT_MODEL).strip()
    if name.lower() == "fake":
        return FakeEmbedder()
    return FastEmbedder(model_name=name)
