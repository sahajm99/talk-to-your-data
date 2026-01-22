"""Tests for text chunking functionality."""

import pytest
from app.ingestion.chunker import chunk_text
from app.ingestion.loaders import RawDocument
from app.ingestion.file_types import FileType
from app.ingestion.chunker import chunk_document


def test_chunk_text_small_text():
    """Test that small text returns at least one chunk."""
    text = "This is a small text that should fit in one chunk."
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    
    assert len(chunks) >= 1
    assert chunks[0][0] == 0  # First chunk has index 0
    assert "small text" in chunks[0][1]


def test_chunk_text_respects_max_tokens():
    """Test that chunks respect max_tokens limit."""
    # Create text with many words
    words = ["word"] * 500
    text = " ".join(words)
    
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    
    # Each chunk should have approximately max_tokens words
    for chunk_index, chunk_text in chunks:
        word_count = len(chunk_text.split())
        # Allow some flexibility (should be close to max_tokens)
        assert word_count <= 100 + 20  # Allow some margin


def test_chunk_text_overlap():
    """Test that chunks have overlap."""
    words = ["word"] * 200
    text = " ".join(words)
    
    chunks = chunk_text(text, max_tokens=50, overlap_tokens=10)
    
    # Should have multiple chunks
    assert len(chunks) > 1
    
    # Check that there's overlap between consecutive chunks
    if len(chunks) >= 2:
        chunk1_words = set(chunks[0][1].split())
        chunk2_words = set(chunks[1][1].split())
        
        # There should be some overlap (at least a few words)
        overlap = chunk1_words.intersection(chunk2_words)
        assert len(overlap) > 0


def test_chunk_text_empty():
    """Test chunking empty text."""
    chunks = chunk_text("", max_tokens=100, overlap_tokens=10)
    
    assert len(chunks) == 1
    assert chunks[0][0] == 0
    assert chunks[0][1] == ""


def test_chunk_document():
    """Test chunk_document creates DocumentChunk instances."""
    raw = RawDocument(
        project_id="test-project",
        source_id="test-doc",
        file_type=FileType.TXT,
        file_name="test.txt",
        bytes=b"word " * 500,  # 500 words
        metadata={"file_path": "/path/to/test.txt"},
    )
    
    text = "word " * 500
    
    # Mock base_metadata
    base_metadata = {"test_key": "test_value"}
    
    chunks = chunk_document("test-project", raw, text, base_metadata)
    
    assert len(chunks) > 0
    
    # Check first chunk
    first_chunk = chunks[0]
    assert first_chunk.project_id == "test-project"
    assert first_chunk.source_id == "test-doc"
    assert first_chunk.file_name == "test.txt"
    assert first_chunk.chunk_index == 0
    assert first_chunk.file_path == "/path/to/test.txt"
    assert "test_key" in first_chunk.metadata
    assert first_chunk.metadata["chunk_index"] == 0
    assert "total_chunks" in first_chunk.metadata

