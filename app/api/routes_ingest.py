"""Document ingestion API endpoints."""

import logging
import pathlib
from pathlib import Path
from typing import Annotated
from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Depends
from app.ingestion.loaders import from_upload_file, from_path
from app.ingestion.pipeline import ingest_multiple_files, ingest_multiple_files_enhanced
from app.ingestion.vector_store import WeaviateVectorStore
from app.ingestion.embedder import BaseEmbedder
from app.models import IngestResponse, DirectoryIngestRequest
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def get_vector_store() -> WeaviateVectorStore:
    """Dependency to get the global vector store instance."""
    from app.main import vector_store
    return vector_store


def get_embedder() -> BaseEmbedder:
    """Dependency to get the global embedder instance."""
    from app.main import embedder
    return embedder


@router.post("/ingest/files", response_model=IngestResponse)
async def ingest_files(
    project_id: Annotated[str, Form()],
    files: Annotated[list[UploadFile], File(...)],
    vector_store: WeaviateVectorStore = Depends(get_vector_store),
    embedder: BaseEmbedder = Depends(get_embedder),
):
    """
    Ingest one or more uploaded files with enhanced visual grounding.

    Now uses Phase 1 enhanced pipeline with:
    - Layout-aware text extraction (PyMuPDF + pdfplumber)
    - Table detection and preservation
    - Semantic chunking with overlap
    - Visual grounding (bounding boxes + chunk images)

    Args:
        project_id: Project/tenant identifier
        files: List of uploaded files
        vector_store: WeaviateVectorStore instance (injected)
        embedder: BaseEmbedder instance (injected)

    Returns:
        IngestResponse with summary for each file
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    logger.info(f"Ingesting {len(files)} files for project {project_id} with enhanced pipeline")

    # Load all files into RawDocument instances
    raws = []
    for file in files:
        try:
            raw = await from_upload_file(project_id, file)
            raws.append(raw)
        except Exception as e:
            logger.error(f"Error loading file {file.filename}: {e}", exc_info=True)
            # Continue with other files even if one fails

    if not raws:
        raise HTTPException(
            status_code=400,
            detail="Failed to load any files"
        )

    # Use enhanced pipeline if USE_VISUAL_GROUNDING is enabled
    data_dir = Path(settings.data_dir)

    if settings.use_visual_grounding:
        logger.info("Using enhanced pipeline with visual grounding")
        summary = await ingest_multiple_files_enhanced(
            project_id=project_id,
            raws=raws,
            vector_store=vector_store,
            embedder=embedder,
            data_dir=data_dir,
            use_visual_grounding=True
        )
    else:
        logger.info("Using legacy pipeline (visual grounding disabled)")
        summary = await ingest_multiple_files(project_id, raws, vector_store, embedder)

    return IngestResponse(project_id=project_id, summary=summary)


@router.post("/ingest/directory")
async def ingest_directory(
    request: DirectoryIngestRequest,
    vector_store: WeaviateVectorStore = Depends(get_vector_store),
    embedder: BaseEmbedder = Depends(get_embedder),
):
    """
    Ingest all files from a directory.
    
    Args:
        request: DirectoryIngestRequest with project_id and path
        vector_store: WeaviateVectorStore instance (injected)
        embedder: BaseEmbedder instance (injected)
    
    Returns:
        IngestResponse with summary for each file found
    """
    directory_path = pathlib.Path(request.path)
    
    if not directory_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Directory not found: {request.path}"
        )
    
    if not directory_path.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is not a directory: {request.path}"
        )
    
    logger.info(f"Ingesting directory {request.path} for project {request.project_id}")
    
    # Find all files in directory
    supported_extensions = {
        '.html', '.htm', '.pdf', '.docx', '.doc',
        '.txt', '.md', '.markdown', '.csv',
        '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'
    }
    
    files = [
        f for f in directory_path.rglob('*')
        if f.is_file() and f.suffix.lower() in supported_extensions
    ]
    
    if not files:
        raise HTTPException(
            status_code=404,
            detail=f"No supported files found in directory: {request.path}"
        )
    
    logger.info(f"Found {len(files)} files to ingest")
    
    # Load all files into RawDocument instances
    raws = []
    for file_path in files:
        try:
            raw = from_path(request.project_id, file_path)
            raws.append(raw)
        except Exception as e:
            logger.error(f"Error loading file {file_path}: {e}", exc_info=True)
            # Continue with other files
    
    if not raws:
        raise HTTPException(
            status_code=400,
            detail="Failed to load any files from directory"
        )
    
    # Use enhanced pipeline if enabled
    data_dir = Path(settings.data_dir)

    if settings.use_visual_grounding:
        logger.info("Using enhanced pipeline with visual grounding for directory ingestion")
        summary = await ingest_multiple_files_enhanced(
            project_id=request.project_id,
            raws=raws,
            vector_store=vector_store,
            embedder=embedder,
            data_dir=data_dir,
            use_visual_grounding=True
        )
    else:
        logger.info("Using legacy pipeline for directory ingestion")
        summary = await ingest_multiple_files(request.project_id, raws, vector_store, embedder)

    return IngestResponse(project_id=request.project_id, summary=summary)

