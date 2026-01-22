"""File loading utilities to create RawDocument instances."""

from dataclasses import dataclass
from typing import Any
import pathlib
from fastapi import UploadFile

from app.ingestion.file_types import FileType, guess_file_type


@dataclass
class RawDocument:
    """Raw document representation before text extraction."""
    
    project_id: str
    source_id: str
    file_type: FileType
    file_name: str
    bytes: bytes
    metadata: dict[str, Any] = None
    
    def __post_init__(self):
        """Initialize metadata if not provided."""
        if self.metadata is None:
            self.metadata = {}


async def from_upload_file(project_id: str, upload_file: UploadFile) -> RawDocument:
    """
    Create a RawDocument from a FastAPI UploadFile.
    
    Args:
        project_id: The project/tenant identifier
        upload_file: FastAPI UploadFile instance
    
    Returns:
        RawDocument instance
    """
    file_name = upload_file.filename or "unknown"
    content = await upload_file.read()
    content_type = upload_file.content_type
    
    file_type = guess_file_type(file_name, content_type)
    
    # Generate source_id from filename (without extension)
    source_id = pathlib.Path(file_name).stem
    
    metadata = {
        "original_filename": file_name,
        "content_type": content_type,
        "file_size": len(content),
    }
    
    return RawDocument(
        project_id=project_id,
        source_id=source_id,
        file_type=file_type,
        file_name=file_name,
        bytes=content,
        metadata=metadata,
    )


def from_path(project_id: str, path: pathlib.Path) -> RawDocument:
    """
    Create a RawDocument from a file path.
    
    Args:
        project_id: The project/tenant identifier
        path: Path to the file
    
    Returns:
        RawDocument instance
    
    Raises:
        FileNotFoundError: If the file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    file_name = path.name
    content = path.read_bytes()
    
    file_type = guess_file_type(file_name, None)
    
    # Generate source_id from filename (without extension)
    source_id = path.stem
    
    metadata = {
        "original_filename": file_name,
        "file_path": str(path.absolute()),
        "file_size": len(content),
    }
    
    return RawDocument(
        project_id=project_id,
        source_id=source_id,
        file_type=file_type,
        file_name=file_name,
        bytes=content,
        metadata=metadata,
    )

