"""File type detection and enumeration."""

from enum import Enum
from typing import Optional
import mimetypes


class FileType(str, Enum):
    """Supported file types for ingestion."""
    
    HTML = "html"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    CSV = "csv"
    IMAGE = "image"
    UNKNOWN = "unknown"


def guess_file_type(filename: str, content_type: Optional[str] = None) -> FileType:
    """
    Guess file type from filename extension and optional MIME type.
    
    Args:
        filename: The filename with extension
        content_type: Optional MIME type (e.g., from HTTP Content-Type header)
    
    Returns:
        FileType enum value
    """
    filename_lower = filename.lower()
    
    # Check by extension first
    if filename_lower.endswith(('.html', '.htm')):
        return FileType.HTML
    elif filename_lower.endswith('.pdf'):
        return FileType.PDF
    elif filename_lower.endswith(('.docx', '.doc')):
        return FileType.DOCX
    elif filename_lower.endswith('.txt'):
        return FileType.TXT
    elif filename_lower.endswith(('.md', '.markdown')):
        return FileType.MARKDOWN
    elif filename_lower.endswith('.csv'):
        return FileType.CSV
    elif filename_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp')):
        return FileType.IMAGE
    
    # Fallback to MIME type if provided
    if content_type:
        if 'html' in content_type:
            return FileType.HTML
        elif 'pdf' in content_type:
            return FileType.PDF
        elif 'wordprocessingml' in content_type or 'msword' in content_type:
            return FileType.DOCX
        elif 'text/plain' in content_type:
            return FileType.TXT
        elif 'text/markdown' in content_type:
            return FileType.MARKDOWN
        elif 'text/csv' in content_type or 'text/comma-separated-values' in content_type:
            return FileType.CSV
        elif content_type.startswith('image/'):
            return FileType.IMAGE
    
    return FileType.UNKNOWN

