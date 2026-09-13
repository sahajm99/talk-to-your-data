"""Pydantic models shared by the store, retrieval, and the API."""

from typing import Any, Literal

from pydantic import BaseModel, Field

RetrievalMode = Literal["hybrid", "keyword", "vector"]


class Chunk(BaseModel):
    """A stored passage of a document."""

    id: int
    doc_id: str
    doc_title: str
    idx: int
    text: str


class DocumentInfo(BaseModel):
    """A document row: what was ingested, for whom, and how big it is."""

    id: str
    title: str
    source: str
    scope: str
    n_chunks: int
    n_chars: int
    created_at: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    document_ids: list[str] = Field(
        default_factory=list,
        description="Empty means every preloaded document plus the session's uploads.",
    )
    mode: RetrievalMode = "hybrid"


class Citation(BaseModel):
    n: int
    chunk_id: int
    doc_id: str
    doc_title: str
    idx: int
    text: str


class RetrievalHit(BaseModel):
    chunk_id: int
    doc_title: str
    idx: int
    score: float
    via: list[str]
    keyword_rank: int | None = None
    vector_rank: int | None = None
    preview: str = Field(description="First 240 characters of the chunk text.")


class AskResponse(BaseModel):
    answer: str
    mode: Literal["groq", "extractive"]
    model: str | None = None
    citations: list[Citation]
    retrieval: list[RetrievalHit]
    latency_ms: int


class AboutInfo(BaseModel):
    generation_mode: str
    model: str | None = None
    embed_model: str
    documents: list[DocumentInfo]
    eval: dict[str, Any] | None = None
    rate_limit: dict[str, Any]
