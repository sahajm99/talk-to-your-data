"""Orchestration pipeline for document ingestion."""

import logging
from pathlib import Path
from typing import Any, Optional
from app.ingestion.loaders import RawDocument
from app.ingestion.text_extractors import extract_text
from app.ingestion.chunker import chunk_document, chunk_document_enhanced
from app.ingestion.embedder import BaseEmbedder
from app.ingestion.vector_store import WeaviateVectorStore
from app.services.document_processor import DocumentProcessor
from app.services.visual_grounding import VisualGroundingService

logger = logging.getLogger(__name__)


async def ingest_raw_document(
    project_id: str,
    raw: RawDocument,
    vector_store: WeaviateVectorStore,
    embedder: BaseEmbedder,
) -> dict[str, Any]:
    """
    Ingest a single raw document through the full pipeline.
    
    Steps:
    1. Extract text and metadata
    2. Chunk the document
    3. Generate embeddings
    4. Store in Weaviate
    
    Args:
        project_id: Project identifier
        raw: RawDocument instance
        vector_store: WeaviateVectorStore instance
        embedder: BaseEmbedder instance
    
    Returns:
        Summary dictionary with ingestion results
    """
    try:
        # Step 1: Extract text
        logger.info(f"Extracting text from {raw.file_name}")
        text, extra_metadata = extract_text(raw)
        
        if not text.strip():
            logger.warning(f"No text extracted from {raw.file_name}")
            return {
                "file_name": raw.file_name,
                "num_chunks": 0,
                "project_id": project_id,
                "source_id": raw.source_id,
                "error": "No text extracted from file",
            }
        
        # Step 2: Prepare base metadata
        base_metadata = {
            "project_id": project_id,
            "file_type": raw.file_type.value,
            **raw.metadata,
            **extra_metadata,
        }
        
        # Step 3: Chunk document
        logger.info(f"Chunking document {raw.file_name}")
        chunks = chunk_document(project_id, raw, text, base_metadata)
        
        if not chunks:
            logger.warning(f"No chunks created from {raw.file_name}")
            return {
                "file_name": raw.file_name,
                "num_chunks": 0,
                "project_id": project_id,
                "source_id": raw.source_id,
                "error": "No chunks created",
            }
        
        # Step 4: Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks")
        chunk_texts = [chunk.text for chunk in chunks]
        embeddings = embedder.embed_texts(chunk_texts)
        
        if len(embeddings) != len(chunks):
            raise ValueError(
                f"Embedding count ({len(embeddings)}) doesn't match "
                f"chunk count ({len(chunks)})"
            )
        
        # Step 5: Store in Weaviate
        logger.info(f"Storing {len(chunks)} chunks in Weaviate")
        vector_store.upsert_chunks(chunks, embeddings)
        
        # Step 6: Return summary
        preview_text = text[:100] + "..." if len(text) > 100 else text
        
        return {
            "file_name": raw.file_name,
            "num_chunks": len(chunks),
            "project_id": project_id,
            "source_id": raw.source_id,
            "text_preview": preview_text,
        }
        
    except Exception as e:
        logger.error(f"Error ingesting {raw.file_name}: {e}", exc_info=True)
        return {
            "file_name": raw.file_name,
            "num_chunks": 0,
            "project_id": project_id,
            "source_id": raw.source_id,
            "error": str(e),
        }


async def ingest_multiple_files(
    project_id: str,
    raws: list[RawDocument],
    vector_store: WeaviateVectorStore,
    embedder: BaseEmbedder,
) -> list[dict[str, Any]]:
    """
    Ingest multiple files sequentially.

    Args:
        project_id: Project identifier
        raws: List of RawDocument instances
        vector_store: WeaviateVectorStore instance
        embedder: BaseEmbedder instance

    Returns:
        List of summary dictionaries (one per file)
    """
    results = []

    for raw in raws:
        logger.info(f"Processing file: {raw.file_name}")
        result = await ingest_raw_document(project_id, raw, vector_store, embedder)
        results.append(result)

    return results


# ============================================================================
# Enhanced ingestion pipeline with visual grounding (Phase 1)
# ============================================================================

async def ingest_raw_document_enhanced(
    project_id: str,
    raw: RawDocument,
    vector_store: WeaviateVectorStore,
    embedder: BaseEmbedder,
    data_dir: Path,
    use_visual_grounding: bool = True
) -> dict[str, Any]:
    """
    Enhanced ingestion pipeline with visual grounding.

    Steps:
    1. Process document with layout awareness (PyMuPDF + pdfplumber)
    2. Chunk with table awareness and overlap
    3. Generate chunk images with bounding boxes
    4. Generate embeddings
    5. Store in Weaviate with visual metadata

    Args:
        project_id: Project identifier
        raw: RawDocument instance
        vector_store: WeaviateVectorStore instance
        embedder: BaseEmbedder instance
        data_dir: Base data directory for storing images
        use_visual_grounding: Whether to generate chunk images

    Returns:
        Summary dictionary with ingestion results
    """
    try:
        from app.config import settings

        # Initialize services
        doc_processor = DocumentProcessor()
        visual_service = VisualGroundingService(data_dir) if use_visual_grounding else None

        # Determine file extension
        file_ext = raw.file_name.split('.')[-1].lower()

        # Step 1: Save uploaded file to disk if not already saved
        file_path = Path(raw.metadata.get('file_path', ''))

        # If file_path doesn't exist or is invalid, save bytes to disk
        if not file_path.exists() or str(file_path) in ['', '.']:
            logger.info(f"Saving uploaded file to disk: {raw.file_name}")

            # Create document directory
            doc_dir = data_dir / "documents" / project_id / raw.source_id
            doc_dir.mkdir(parents=True, exist_ok=True)

            # Save file with appropriate extension
            file_path = doc_dir / f"original.{file_ext}"
            file_path.write_bytes(raw.bytes)

            # Update metadata
            raw.metadata['file_path'] = str(file_path.absolute())

            logger.info(f"File saved to: {file_path}")

        # Step 2: Process document based on type
        if file_ext == 'pdf':
            logger.info(f"Processing PDF with layout awareness: {raw.file_name}")

            if not file_path.exists():
                raise FileNotFoundError(f"PDF file not found: {file_path}")

            # Extract text blocks with bounding boxes
            blocks, doc_metadata = doc_processor.process_pdf(file_path)

            if not blocks:
                logger.warning(f"No content extracted from {raw.file_name}")
                return {
                    "file_name": raw.file_name,
                    "num_chunks": 0,
                    "project_id": project_id,
                    "source_id": raw.source_id,
                    "error": "No content extracted from PDF",
                }

        elif file_ext in ['docx', 'doc']:
            logger.info(f"Processing DOCX: {raw.file_name}")

            if not file_path.exists():
                raise FileNotFoundError(f"DOCX file not found: {file_path}")

            blocks, doc_metadata = doc_processor.process_docx(file_path)

        else:
            # Fall back to legacy extraction for other formats
            logger.info(f"Using legacy extraction for {raw.file_name}")
            return await ingest_raw_document(project_id, raw, vector_store, embedder)

        # Step 2: Chunk document with semantic chunking
        logger.info(f"Chunking {len(blocks)} blocks from {raw.file_name}")
        enhanced_chunks = chunk_document_enhanced(
            project_id=project_id,
            document_id=raw.source_id,
            file_name=raw.file_name,
            file_path=str(file_path),
            blocks=blocks,
            chunk_size=settings.chunk_max_tokens,
            chunk_overlap=settings.chunk_overlap_tokens
        )

        if not enhanced_chunks:
            logger.warning(f"No chunks created from {raw.file_name}")
            return {
                "file_name": raw.file_name,
                "num_chunks": 0,
                "project_id": project_id,
                "source_id": raw.source_id,
                "error": "No chunks created",
            }

        # Step 3: Generate chunk images (only for PDFs with visual grounding)
        image_paths = []
        if use_visual_grounding and visual_service and file_ext == 'pdf':
            logger.info(f"Generating chunk images for {len(enhanced_chunks)} chunks")
            image_paths = visual_service.generate_chunk_images(
                pdf_path=file_path,
                chunks=enhanced_chunks,
                project_id=project_id,
                document_id=raw.source_id
            )
        else:
            image_paths = [""] * len(enhanced_chunks)

        # Step 4: Generate embeddings
        logger.info(f"Generating embeddings for {len(enhanced_chunks)} chunks")
        chunk_texts = [chunk.text for chunk in enhanced_chunks]
        embeddings = embedder.embed_texts(chunk_texts)

        if len(embeddings) != len(enhanced_chunks):
            raise ValueError(
                f"Embedding count ({len(embeddings)}) doesn't match "
                f"chunk count ({len(enhanced_chunks)})"
            )

        # Step 5: Store in Weaviate with visual grounding
        logger.info(f"Storing {len(enhanced_chunks)} enhanced chunks in Weaviate")
        vector_store.upsert_chunks_enhanced(
            chunks=enhanced_chunks,
            embeddings=embeddings,
            image_paths=image_paths
        )

        # Step 6: Return summary
        total_text = " ".join(block.text for block in blocks)
        preview_text = total_text[:100] + "..." if len(total_text) > 100 else total_text

        return {
            "file_name": raw.file_name,
            "num_chunks": len(enhanced_chunks),
            "project_id": project_id,
            "source_id": raw.source_id,
            "text_preview": preview_text,
            "page_count": doc_metadata.get("page_count", 0),
            "has_visual_grounding": use_visual_grounding and file_ext == 'pdf',
            "tables_detected": sum(1 for c in enhanced_chunks if c.chunk_type == "table"),
        }

    except Exception as e:
        logger.error(f"Error ingesting {raw.file_name} with enhanced pipeline: {e}", exc_info=True)
        return {
            "file_name": raw.file_name,
            "num_chunks": 0,
            "project_id": project_id,
            "source_id": raw.source_id,
            "error": str(e),
        }


async def ingest_multiple_files_enhanced(
    project_id: str,
    raws: list[RawDocument],
    vector_store: WeaviateVectorStore,
    embedder: BaseEmbedder,
    data_dir: Path,
    use_visual_grounding: bool = True
) -> list[dict[str, Any]]:
    """
    Ingest multiple files with enhanced pipeline.

    Args:
        project_id: Project identifier
        raws: List of RawDocument instances
        vector_store: WeaviateVectorStore instance
        embedder: BaseEmbedder instance
        data_dir: Base data directory
        use_visual_grounding: Whether to use visual grounding

    Returns:
        List of summary dictionaries
    """
    results = []

    for raw in raws:
        logger.info(f"Processing file with enhanced pipeline: {raw.file_name}")
        result = await ingest_raw_document_enhanced(
            project_id=project_id,
            raw=raw,
            vector_store=vector_store,
            embedder=embedder,
            data_dir=data_dir,
            use_visual_grounding=use_visual_grounding
        )
        results.append(result)

    return results

