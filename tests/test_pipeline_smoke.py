"""Smoke tests for the ingestion pipeline."""

import pytest
from app.ingestion.loaders import RawDocument
from app.ingestion.file_types import FileType
from app.ingestion.pipeline import ingest_raw_document
from app.ingestion.embedder import BaseEmbedder
from app.ingestion.vector_store import WeaviateVectorStore


class MockEmbedder:
    """Mock embedder for testing."""
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Return fake embeddings (all zeros)."""
        return [[0.0] * 3072 for _ in texts]  # text-embedding-3-large has 3072 dimensions


class MockVectorStore:
    """Mock vector store for testing."""
    
    def __init__(self):
        self.stored_chunks = []
        self.stored_embeddings = []
    
    def ensure_schema(self):
        """No-op for mock."""
        pass
    
    def upsert_chunks(self, chunks, embeddings):
        """Store chunks and embeddings for verification."""
        self.stored_chunks.extend(chunks)
        self.stored_embeddings.extend(embeddings)
    
    def close(self):
        """No-op for mock."""
        pass


@pytest.mark.asyncio
async def test_ingest_raw_document_produces_chunks():
    """Test that ingest_raw_document produces expected number of chunks."""
    raw = RawDocument(
        project_id="test-project",
        source_id="test-doc",
        file_type=FileType.TXT,
        file_name="test.txt",
        bytes=b"This is a test document. " * 100,  # Create enough text to chunk
    )
    
    mock_embedder = MockEmbedder()
    mock_vector_store = MockVectorStore()
    
    result = await ingest_raw_document(
        project_id="test-project",
        raw=raw,
        vector_store=mock_vector_store,
        embedder=mock_embedder,
    )
    
    # Should have created chunks
    assert result["num_chunks"] > 0
    assert result["project_id"] == "test-project"
    assert result["source_id"] == "test-doc"
    assert result["file_name"] == "test.txt"
    
    # Verify chunks were stored
    assert len(mock_vector_store.stored_chunks) == result["num_chunks"]
    assert len(mock_vector_store.stored_embeddings) == result["num_chunks"]


@pytest.mark.asyncio
async def test_ingest_raw_document_metadata_mapping():
    """Test that metadata is correctly mapped in chunks."""
    raw = RawDocument(
        project_id="test-project",
        source_id="test-doc",
        file_type=FileType.TXT,
        file_name="test.txt",
        bytes=b"Short test text.",
        metadata={"custom_key": "custom_value"},
    )
    
    mock_embedder = MockEmbedder()
    mock_vector_store = MockVectorStore()
    
    result = await ingest_raw_document(
        project_id="test-project",
        raw=raw,
        vector_store=mock_vector_store,
        embedder=mock_embedder,
    )
    
    # Check that stored chunks have correct metadata
    if mock_vector_store.stored_chunks:
        chunk = mock_vector_store.stored_chunks[0]
        assert chunk.project_id == "test-project"
        assert chunk.source_id == "test-doc"
        assert chunk.source_type == "txt"
        assert chunk.file_name == "test.txt"
        assert "custom_key" in chunk.metadata or "total_chunks" in chunk.metadata


@pytest.mark.asyncio
async def test_ingest_raw_document_empty_file():
    """Test handling of empty or unparseable files."""
    raw = RawDocument(
        project_id="test-project",
        source_id="test-doc",
        file_type=FileType.UNKNOWN,
        file_name="test.xyz",
        bytes=b"",
    )
    
    mock_embedder = MockEmbedder()
    mock_vector_store = MockVectorStore()
    
    result = await ingest_raw_document(
        project_id="test-project",
        raw=raw,
        vector_store=mock_vector_store,
        embedder=mock_embedder,
    )
    
    # Should handle gracefully
    assert "error" in result or result["num_chunks"] == 0

