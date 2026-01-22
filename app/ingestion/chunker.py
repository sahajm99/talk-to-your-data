"""
Enhanced semantic chunking with overlap and table awareness.

This module provides intelligent document chunking that:
- Respects document structure (paragraphs, sections)
- Keeps tables as single chunks
- Adds overlap between chunks for context
- Preserves bounding box information
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from app.ingestion.loaders import RawDocument
from app.models import DocumentChunk

logger = logging.getLogger(__name__)


# ============================================================================
# Legacy chunking functions (for backward compatibility)
# ============================================================================

def chunk_text(text: str, max_tokens: int, overlap_tokens: int) -> list[tuple[int, str]]:
    """
    Chunk text into smaller pieces with overlap.

    Uses word-based approximation of tokens (splits on whitespace).

    Args:
        text: The text to chunk
        max_tokens: Maximum number of words per chunk
        overlap_tokens: Number of words to overlap between chunks

    Returns:
        List of (chunk_index, chunk_text) tuples
    """
    if not text.strip():
        return [(0, text)]

    words = text.split()

    if len(words) <= max_tokens:
        return [(0, text)]

    chunks = []
    chunk_index = 0
    start = 0

    while start < len(words):
        end = start + max_tokens
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        chunks.append((chunk_index, chunk_text))

        chunk_index += 1
        # Move start forward by (max_tokens - overlap_tokens) to create overlap
        start += max_tokens - overlap_tokens

        # Prevent infinite loop if overlap is too large
        if overlap_tokens >= max_tokens:
            break

    return chunks


def chunk_document(
    project_id: str,
    raw: RawDocument,
    text: str,
    base_metadata: dict[str, Any],
) -> list[DocumentChunk]:
    """
    Chunk a document and create DocumentChunk instances.

    This is the legacy function that maintains backward compatibility.
    For enhanced chunking with visual grounding, use chunk_document_enhanced.

    Args:
        project_id: The project identifier
        raw: RawDocument instance
        text: Extracted text from the document
        base_metadata: Base metadata dictionary to merge

    Returns:
        List of DocumentChunk instances
    """
    from app.config import settings

    chunks_data = chunk_text(
        text,
        max_tokens=settings.chunk_max_tokens,
        overlap_tokens=settings.chunk_overlap_tokens,
    )

    total_chunks = len(chunks_data)

    document_chunks = []
    for chunk_index, chunk_content in chunks_data:
        # Merge base_metadata with chunk-specific metadata
        chunk_metadata = {
            **base_metadata,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
        }

        chunk = DocumentChunk(
            project_id=project_id,
            source_id=raw.source_id,
            source_type=raw.file_type.value,
            file_name=raw.file_name,
            file_path=raw.metadata.get("file_path"),
            chunk_index=chunk_index,
            text=chunk_content,
            metadata=chunk_metadata,
        )

        document_chunks.append(chunk)

    return document_chunks


# ============================================================================
# Enhanced semantic chunking with visual grounding
# ============================================================================

class BoundingBox:
    """Represents a bounding box with coordinates."""

    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        self.x1 = x1
        self.y1 = y1
        self.x2 = x2
        self.y2 = y2

    def to_list(self) -> List[float]:
        """Convert to list format [x1, y1, x2, y2]."""
        return [self.x1, self.y1, self.x2, self.y2]

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {"x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2}

    @classmethod
    def merge(cls, boxes: List["BoundingBox"]) -> "BoundingBox":
        """Merge multiple bounding boxes into one encompassing box."""
        if not boxes:
            return cls(0, 0, 0, 0)

        x1 = min(box.x1 for box in boxes)
        y1 = min(box.y1 for box in boxes)
        x2 = max(box.x2 for box in boxes)
        y2 = max(box.y2 for box in boxes)

        return cls(x1, y1, x2, y2)


class EnhancedDocumentChunk:
    """Enhanced chunk with visual grounding metadata."""

    def __init__(
        self,
        chunk_id: str,
        text: str,
        chunk_type: str,
        page_number: int,
        bounding_box: List[float],  # [x1, y1, x2, y2]
        chunk_index: int,
        document_id: str,
        project_id: str,
        file_name: str,
        file_path: Optional[str] = None,
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.chunk_id = chunk_id
        self.text = text
        self.chunk_type = chunk_type
        self.page_number = page_number
        self.bounding_box = bounding_box
        self.chunk_index = chunk_index
        self.document_id = document_id
        self.project_id = project_id
        self.file_name = file_name
        self.file_path = file_path
        self.confidence = confidence
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "chunk_id": self.chunk_id,
            "text": self.text,
            "chunk_type": self.chunk_type,
            "page_number": self.page_number,
            "bounding_box": self.bounding_box,
            "chunk_index": self.chunk_index,
            "document_id": self.document_id,
            "project_id": self.project_id,
            "file_name": self.file_name,
            "file_path": self.file_path,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


class SemanticChunker:
    """
    Intelligent chunker that respects document structure.

    Features:
    - Configurable chunk size (target word count)
    - Overlap between chunks for context
    - Table-aware (keeps tables whole)
    - Preserves bounding boxes
    - Respects paragraph boundaries
    """

    def __init__(
        self,
        chunk_size: int = 400,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.logger = logging.getLogger(__name__)

    def chunk_blocks(
        self,
        blocks: List[Any],  # TextBlock objects from document_processor
        document_id: str,
        project_id: str,
        file_name: str,
        file_path: Optional[str] = None
    ) -> List[EnhancedDocumentChunk]:
        """
        Chunk a document from text blocks with visual grounding.

        Args:
            blocks: List of TextBlock objects from document processor
            document_id: Unique document identifier
            project_id: Project identifier
            file_name: Original file name
            file_path: Optional file path

        Returns:
            List of EnhancedDocumentChunk objects
        """
        chunks = []
        chunk_index = 0

        # Separate tables from text blocks
        table_blocks = [b for b in blocks if getattr(b, 'block_type', 'text') == "table"]
        text_blocks = [b for b in blocks if getattr(b, 'block_type', 'text') != "table"]

        # Process tables first (each table is a single chunk)
        for table_block in table_blocks:
            bbox = getattr(table_block, 'bbox', None)
            bbox_list = bbox.to_list() if bbox else [0, 0, 0, 0]

            chunk = EnhancedDocumentChunk(
                chunk_id=f"{document_id}_chunk_{chunk_index}",
                text=table_block.text,
                chunk_type="table",
                page_number=getattr(table_block, 'page_number', 1),
                bounding_box=bbox_list,
                chunk_index=chunk_index,
                document_id=document_id,
                project_id=project_id,
                file_name=file_name,
                file_path=file_path,
                confidence=getattr(table_block, 'confidence', 1.0),
                metadata=getattr(table_block, 'metadata', {})
            )
            chunks.append(chunk)
            chunk_index += 1

        # Process text blocks with semantic chunking
        text_chunks = self._chunk_text_blocks(
            text_blocks,
            document_id,
            project_id,
            file_name,
            file_path,
            start_index=chunk_index
        )

        chunks.extend(text_chunks)

        # Sort by page and position
        chunks.sort(key=lambda c: (c.page_number, c.chunk_index))

        # Renumber indices
        for i, chunk in enumerate(chunks):
            chunk.chunk_index = i
            chunk.chunk_id = f"{document_id}_chunk_{i}"

        self.logger.info(
            f"Created {len(chunks)} enhanced chunks "
            f"({len(table_blocks)} tables, {len(text_chunks)} text)"
        )

        return chunks

    def _chunk_text_blocks(
        self,
        blocks: List[Any],
        document_id: str,
        project_id: str,
        file_name: str,
        file_path: Optional[str],
        start_index: int = 0
    ) -> List[EnhancedDocumentChunk]:
        """Chunk text blocks with overlap."""
        chunks = []
        current_text = []
        current_blocks = []
        chunk_index = start_index

        for block in blocks:
            # Skip headers/footers if needed
            if getattr(block, 'block_type', 'text') in ["header", "footer"]:
                continue

            current_text.append(block.text)
            current_blocks.append(block)

            # Check if reached target size
            total_words = sum(len(text.split()) for text in current_text)

            if total_words >= self.chunk_size:
                chunk = self._create_chunk_from_blocks(
                    current_blocks,
                    document_id,
                    project_id,
                    file_name,
                    file_path,
                    chunk_index
                )

                if chunk:
                    chunks.append(chunk)
                    chunk_index += 1

                # Prepare next chunk with overlap
                overlap_text = self._get_overlap_text(current_text)
                overlap_blocks = self._get_overlap_blocks(current_blocks, overlap_text)

                current_text = [overlap_text] if overlap_text else []
                current_blocks = overlap_blocks

        # Final chunk
        if current_text:
            chunk = self._create_chunk_from_blocks(
                current_blocks,
                document_id,
                project_id,
                file_name,
                file_path,
                chunk_index
            )

            if chunk:
                chunks.append(chunk)

        return chunks

    def _create_chunk_from_blocks(
        self,
        blocks: List[Any],
        document_id: str,
        project_id: str,
        file_name: str,
        file_path: Optional[str],
        chunk_index: int
    ) -> Optional[EnhancedDocumentChunk]:
        """Create chunk from blocks."""
        if not blocks:
            return None

        text = "\n\n".join(block.text for block in blocks)

        if len(text.split()) < self.min_chunk_size:
            return None

        # Merge bounding boxes
        bboxes = [getattr(b, 'bbox', None) for b in blocks if hasattr(b, 'bbox')]
        if bboxes:
            merged_bbox = BoundingBox.merge(bboxes)
            bbox_list = merged_bbox.to_list()
        else:
            bbox_list = [0, 0, 0, 0]

        page_number = getattr(blocks[0], 'page_number', 1)
        avg_confidence = sum(getattr(b, 'confidence', 1.0) for b in blocks) / len(blocks)

        return EnhancedDocumentChunk(
            chunk_id=f"{document_id}_chunk_{chunk_index}",
            text=text,
            chunk_type="text",
            page_number=page_number,
            bounding_box=bbox_list,
            chunk_index=chunk_index,
            document_id=document_id,
            project_id=project_id,
            file_name=file_name,
            file_path=file_path,
            confidence=avg_confidence,
            metadata={
                "block_count": len(blocks),
                "word_count": len(text.split())
            }
        )

    def _get_overlap_text(self, texts: List[str]) -> str:
        """Get overlap text from end of current chunk."""
        if not texts:
            return ""

        combined = " ".join(texts)
        words = combined.split()

        if len(words) <= self.chunk_overlap:
            return combined

        return " ".join(words[-self.chunk_overlap:])

    def _get_overlap_blocks(self, blocks: List[Any], overlap_text: str) -> List[Any]:
        """Get blocks for overlap."""
        if not overlap_text or not blocks:
            return []

        overlap_word_count = len(overlap_text.split())
        overlap_blocks = []
        word_count = 0

        for block in reversed(blocks):
            overlap_blocks.insert(0, block)
            word_count += len(block.text.split())

            if word_count >= overlap_word_count:
                break

        return overlap_blocks


def chunk_document_enhanced(
    project_id: str,
    document_id: str,
    file_name: str,
    file_path: Optional[str],
    blocks: List[Any],
    chunk_size: int = 400,
    chunk_overlap: int = 50
) -> List[EnhancedDocumentChunk]:
    """
    Enhanced chunking with visual grounding.

    Args:
        project_id: Project identifier
        document_id: Document identifier
        file_name: File name
        file_path: Optional file path
        blocks: List of TextBlock objects
        chunk_size: Target chunk size
        chunk_overlap: Overlap size

    Returns:
        List of EnhancedDocumentChunk objects
    """
    chunker = SemanticChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )

    return chunker.chunk_blocks(
        blocks=blocks,
        document_id=document_id,
        project_id=project_id,
        file_name=file_name,
        file_path=file_path
    )
