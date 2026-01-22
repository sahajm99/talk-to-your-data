"""Text extraction from various file formats."""

import csv
import io
import re
from typing import Any
from bs4 import BeautifulSoup
import pdfplumber
from docx import Document

from app.ingestion.loaders import RawDocument
from app.ingestion.file_types import FileType


def extract_text(raw: RawDocument) -> tuple[str, dict[str, Any]]:
    """
    Extract clean text from a RawDocument.
    
    Args:
        raw: RawDocument instance
    
    Returns:
        Tuple of (extracted_text, extra_metadata)
    """
    file_type = raw.file_type
    extra_metadata: dict[str, Any] = {}
    
    if file_type == FileType.HTML:
        text, metadata = _extract_html(raw.bytes)
        extra_metadata.update(metadata)
    elif file_type == FileType.PDF:
        text, metadata = _extract_pdf(raw.bytes)
        extra_metadata.update(metadata)
    elif file_type == FileType.DOCX:
        text = _extract_docx(raw.bytes)
    elif file_type in (FileType.TXT, FileType.MARKDOWN):
        text = _extract_text_file(raw.bytes)
    elif file_type == FileType.CSV:
        text = _extract_csv(raw.bytes)
    elif file_type == FileType.IMAGE:
        text = f"IMAGE: {raw.file_name} (no OCR yet)"
        extra_metadata["ocr_note"] = "OCR not implemented yet"
    else:
        text = f"UNKNOWN FILE TYPE: {raw.file_name}"
        extra_metadata["error"] = f"Unsupported file type: {file_type}"
    
    # Normalize whitespace
    text = _normalize_whitespace(text)
    
    return text, extra_metadata


def _extract_html(content: bytes) -> tuple[str, dict[str, Any]]:
    """
    Extract text from HTML content.
    
    Removes script/style tags, extracts text, and includes image alt text.
    """
    soup = BeautifulSoup(content, 'html.parser')
    
    # Remove script, style, and noscript tags
    for tag in soup(['script', 'style', 'noscript']):
        tag.decompose()
    
    # Extract text
    text = soup.get_text("\n")
    
    # Extract image information
    images = []
    for img in soup.find_all('img'):
        alt = img.get('alt', '')
        src = img.get('src', '')
        filename = src.split('/')[-1] if src else 'unknown'
        image_text = alt if alt else filename
        images.append(f"Image: {image_text}")
    
    # Append image information to text
    if images:
        text += "\n\n" + "\n".join(images)
    
    metadata = {
        "image_count": len(images),
    }
    
    return text, metadata


def _extract_pdf(content: bytes) -> tuple[str, dict[str, Any]]:
    """
    Extract text from PDF content.
    
    Extracts page by page with page separators.
    """
    pages_text = []
    page_count = 0
    
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text()
            if page_text:
                pages_text.append(f"\n\n--- Page {i} ---\n\n{page_text}")
    
    text = "".join(pages_text)
    
    metadata = {
        "page_count": page_count,
    }
    
    return text, metadata


def _extract_docx(content: bytes) -> str:
    """
    Extract text from DOCX content.
    
    Iterates through paragraphs and joins with newlines.
    """
    doc = Document(io.BytesIO(content))
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_text_file(content: bytes) -> str:
    """
    Extract text from plain text or markdown file.
    
    Decodes as UTF-8 with error handling.
    """
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        # Fallback to latin-1 or ignore errors
        return content.decode('utf-8', errors='ignore')


def _extract_csv(content: bytes) -> str:
    """
    Extract text from CSV content.
    
    Converts CSV to plain text format: header row followed by data rows.
    """
    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        text_content = content.decode('utf-8', errors='ignore')
    
    csv_reader = csv.reader(io.StringIO(text_content))
    rows = []
    
    for row in csv_reader:
        rows.append(", ".join(row))
    
    return "\n".join(rows)


def _normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in extracted text.
    
    - Removes excessive blank lines (more than 2 consecutive newlines)
    - Strips leading/trailing whitespace from each line
    - Normalizes spaces
    """
    # Replace multiple consecutive newlines (3+) with double newline
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Strip each line and remove empty lines at start/end
    lines = [line.strip() for line in text.split('\n')]
    
    # Remove leading and trailing empty lines
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    
    # Normalize spaces (multiple spaces to single space)
    normalized_lines = [re.sub(r' +', ' ', line) for line in lines]
    
    return '\n'.join(normalized_lines)

