"""Tests for text extraction from various file types."""

import pytest
from app.ingestion.loaders import RawDocument
from app.ingestion.file_types import FileType
from app.ingestion.text_extractors import extract_text


def test_html_extraction():
    """Test HTML extraction removes script/style tags and includes image alt text."""
    html_content = b"""
    <html>
    <head>
        <script>alert('test');</script>
        <style>body { color: red; }</style>
    </head>
    <body>
        <h1>Main Heading</h1>
        <p>This is a paragraph.</p>
        <img src="image.jpg" alt="Test Image">
        <noscript>No script content</noscript>
    </body>
    </html>
    """
    
    raw = RawDocument(
        project_id="test",
        source_id="test",
        file_type=FileType.HTML,
        file_name="test.html",
        bytes=html_content,
    )
    
    text, metadata = extract_text(raw)
    
    # Should not contain script or style content
    assert "alert('test')" not in text
    assert "body { color: red; }" not in text
    assert "No script content" not in text
    
    # Should contain heading and paragraph
    assert "Main Heading" in text
    assert "This is a paragraph" in text
    
    # Should include image alt text
    assert "Image: Test Image" in text or "image.jpg" in text
    
    # Should have image count in metadata
    assert "image_count" in metadata


def test_html_extraction_no_images():
    """Test HTML extraction when there are no images."""
    html_content = b"<html><body><p>Simple text</p></body></html>"
    
    raw = RawDocument(
        project_id="test",
        source_id="test",
        file_type=FileType.HTML,
        file_name="test.html",
        bytes=html_content,
    )
    
    text, metadata = extract_text(raw)
    
    assert "Simple text" in text
    assert metadata.get("image_count") == 0


def test_text_file_extraction():
    """Test plain text file extraction."""
    text_content = b"This is a simple text file.\nWith multiple lines."
    
    raw = RawDocument(
        project_id="test",
        source_id="test",
        file_type=FileType.TXT,
        file_name="test.txt",
        bytes=text_content,
    )
    
    text, metadata = extract_text(raw)
    
    assert "This is a simple text file" in text
    assert "With multiple lines" in text


def test_image_extraction_placeholder():
    """Test that images return placeholder text."""
    raw = RawDocument(
        project_id="test",
        source_id="test",
        file_type=FileType.IMAGE,
        file_name="test.jpg",
        bytes=b"fake image bytes",
    )
    
    text, metadata = extract_text(raw)
    
    assert "IMAGE: test.jpg" in text
    assert "no OCR yet" in text
    assert "ocr_note" in metadata


def test_unknown_file_type():
    """Test handling of unknown file types."""
    raw = RawDocument(
        project_id="test",
        source_id="test",
        file_type=FileType.UNKNOWN,
        file_name="test.xyz",
        bytes=b"some content",
    )
    
    text, metadata = extract_text(raw)
    
    assert "UNKNOWN FILE TYPE" in text
    assert "error" in metadata

