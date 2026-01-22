"""Pydantic models for request/response types and data structures."""

from pydantic import BaseModel, Field
from typing import Any, Optional
from datetime import datetime


class DocumentChunk(BaseModel):
    """Represents a chunk of a document with metadata."""
    
    project_id: str
    source_id: str
    source_type: str
    file_name: str
    file_path: Optional[str] = None
    chunk_index: int
    text: str
    metadata: dict[str, Any] = {}


class IngestResponse(BaseModel):
    """Response model for ingestion endpoints."""
    
    project_id: str
    summary: list[dict[str, Any]]


class DirectoryIngestRequest(BaseModel):
    """Request model for directory ingestion."""

    project_id: str
    path: str


# ============================================================================
# Chat & RAG Models (Phase 2)
# ============================================================================

class SourceReference(BaseModel):
    """Reference to a source chunk with visual grounding data."""

    chunk_id: str
    source_id: str
    file_name: str
    page_number: Optional[int] = None
    chunk_index: int
    text: str
    score: float = Field(description="Relevance score from vector search")

    # Visual grounding metadata
    bounding_box: Optional[list[float]] = Field(
        default=None,
        description="Bounding box coordinates [x1, y1, x2, y2]"
    )
    image_path: Optional[str] = Field(
        default=None,
        description="Path to chunk image (relative to data directory)"
    )
    chunk_type: Optional[str] = Field(
        default="text",
        description="Type of chunk: text, table, image"
    )


class ConversationMessage(BaseModel):
    """Single message in a conversation."""

    role: str = Field(description="Role: 'user' or 'assistant'")
    content: str = Field(description="Message content")
    timestamp: datetime = Field(default_factory=datetime.now)
    sources: Optional[list[SourceReference]] = Field(
        default=None,
        description="Source references (only for assistant messages)"
    )


class ChatQuery(BaseModel):
    """Request model for chat queries."""

    project_id: str = Field(description="Project/tenant identifier")
    query: str = Field(description="User's question", min_length=1)
    session_id: Optional[str] = Field(
        default=None,
        description="Session ID for conversation continuity"
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Number of relevant chunks to retrieve"
    )
    include_images: bool = Field(
        default=True,
        description="Whether to include image paths in response"
    )


class ChatResponse(BaseModel):
    """Response model for chat queries."""

    answer: str = Field(description="Generated answer from the LLM")
    sources: list[SourceReference] = Field(
        default_factory=list,
        description="Source chunks used to generate the answer"
    )
    session_id: str = Field(description="Session ID for this conversation")
    query: str = Field(description="Original user query")
    project_id: str = Field(description="Project identifier")

    # Optional metadata
    retrieval_time_ms: Optional[float] = Field(
        default=None,
        description="Time taken for vector search (milliseconds)"
    )
    generation_time_ms: Optional[float] = Field(
        default=None,
        description="Time taken for LLM generation (milliseconds)"
    )
    total_time_ms: Optional[float] = Field(
        default=None,
        description="Total processing time (milliseconds)"
    )

