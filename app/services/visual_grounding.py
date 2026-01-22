"""
Visual grounding service for generating chunk images.

This module handles:
- Cropping chunks from PDF pages using bounding boxes
- Adding highlight overlays to cropped images
- Saving images to organized directory structure
- Generating full-page views with highlights
"""

import logging
import io
from pathlib import Path
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


class VisualGroundingService:
    """
    Service for visual grounding: cropping and highlighting document chunks.

    Features:
    - Crop chunk regions from PDFs
    - Add colored highlight borders
    - Save to organized directory structure
    - Support for multiple DPI resolutions
    """

    def __init__(self, data_dir: Path, highlight_color: str = "red", highlight_width: int = 5):
        """
        Initialize visual grounding service.

        Args:
            data_dir: Base data directory (e.g., 'data/')
            highlight_color: Color for highlight border
            highlight_width: Width of highlight border in pixels
        """
        self.data_dir = Path(data_dir)
        self.highlight_color = highlight_color
        self.highlight_width = highlight_width
        self.logger = logging.getLogger(__name__)

    def crop_chunk_image(
        self,
        pdf_path: Path,
        page_number: int,
        bounding_box: List[float],  # [x1, y1, x2, y2]
        output_path: Path,
        add_highlight: bool = True,
        padding: int = 10,
        dpi: int = 144
    ) -> Optional[Path]:
        """
        Crop a chunk region from a PDF page and save as image.

        Args:
            pdf_path: Path to original PDF file
            page_number: Page number (1-indexed)
            bounding_box: Bounding box [x1, y1, x2, y2]
            output_path: Where to save the cropped image
            add_highlight: Whether to add highlight border
            padding: Padding around bounding box in points
            dpi: Resolution for rendering (144 = 2x, 72 = 1x)

        Returns:
            Path to saved image, or None if failed
        """
        try:
            # Open PDF
            doc = fitz.open(pdf_path)

            # Get page (0-indexed)
            page_idx = page_number - 1
            if page_idx < 0 or page_idx >= len(doc):
                self.logger.error(f"Invalid page number: {page_number}")
                doc.close()
                return None

            page = doc[page_idx]

            # Create rectangle with padding
            x1, y1, x2, y2 = bounding_box
            rect = fitz.Rect(
                max(0, x1 - padding),
                max(0, y1 - padding),
                min(page.rect.width, x2 + padding),
                min(page.rect.height, y2 + padding)
            )

            # Calculate zoom factor for DPI
            # Default PDF DPI is 72, so zoom = target_dpi / 72
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)

            # Render page region to pixmap
            pix = page.get_pixmap(clip=rect, matrix=mat)

            # Convert to PNG bytes
            img_bytes = pix.tobytes("png")

            # Convert to PIL Image
            img = Image.open(io.BytesIO(img_bytes))

            # Add highlight border
            if add_highlight:
                img = self._add_highlight_border(img)

            # Create output directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Save image
            img.save(output_path, "PNG", optimize=True)

            doc.close()

            self.logger.debug(f"Created chunk image: {output_path.name}")
            return output_path

        except Exception as e:
            self.logger.error(f"Error cropping chunk image: {e}", exc_info=True)
            return None

    def _add_highlight_border(self, img: Image.Image) -> Image.Image:
        """
        Add colored highlight border around image.

        Args:
            img: PIL Image

        Returns:
            Image with highlight border
        """
        draw = ImageDraw.Draw(img)

        # Draw rectangle around entire image
        width, height = img.size
        for i in range(self.highlight_width):
            draw.rectangle(
                [(i, i), (width - i - 1, height - i - 1)],
                outline=self.highlight_color,
                width=1
            )

        return img

    def generate_chunk_images(
        self,
        pdf_path: Path,
        chunks: List[Any],  # EnhancedDocumentChunk objects
        project_id: str,
        document_id: str
    ) -> List[str]:
        """
        Generate cropped images for all chunks in a document.

        Args:
            pdf_path: Path to original PDF
            chunks: List of EnhancedDocumentChunk objects
            project_id: Project identifier
            document_id: Document identifier

        Returns:
            List of relative image paths (relative to data_dir)
        """
        image_paths = []

        # Create images directory
        images_dir = self.data_dir / "documents" / project_id / document_id / "chunk_images"
        images_dir.mkdir(parents=True, exist_ok=True)

        for chunk in chunks:
            # Skip if no bounding box or invalid
            bbox = getattr(chunk, 'bounding_box', [0, 0, 0, 0])
            if bbox == [0, 0, 0, 0]:
                # No visual grounding for this chunk
                image_paths.append("")
                continue

            # Generate image filename
            chunk_id = getattr(chunk, 'chunk_id', f"chunk_{getattr(chunk, 'chunk_index', 0)}")
            page_num = getattr(chunk, 'page_number', 1)
            output_path = images_dir / f"{chunk_id}_page_{page_num}.png"

            # Crop and save image
            result = self.crop_chunk_image(
                pdf_path=pdf_path,
                page_number=page_num,
                bounding_box=bbox,
                output_path=output_path,
                add_highlight=True
            )

            if result:
                # Store relative path
                rel_path = str(output_path.relative_to(self.data_dir))
                image_paths.append(rel_path)
            else:
                image_paths.append("")

        self.logger.info(
            f"Generated {sum(1 for p in image_paths if p)} chunk images "
            f"out of {len(chunks)} chunks"
        )

        return image_paths

    def generate_full_page_with_highlight(
        self,
        pdf_path: Path,
        page_number: int,
        bounding_box: List[float],
        output_path: Path,
        dpi: int = 144
    ) -> Optional[Path]:
        """
        Generate full page image with chunk highlighted.

        Args:
            pdf_path: Path to PDF
            page_number: Page number (1-indexed)
            bounding_box: Bounding box to highlight [x1, y1, x2, y2]
            output_path: Where to save image
            dpi: Resolution

        Returns:
            Path to saved image, or None if failed
        """
        try:
            doc = fitz.open(pdf_path)
            page_idx = page_number - 1

            if page_idx < 0 or page_idx >= len(doc):
                doc.close()
                return None

            page = doc[page_idx]

            # Render full page
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img_bytes = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_bytes))

            # Draw highlight rectangle on full page
            draw = ImageDraw.Draw(img)

            # Scale bounding box coordinates by zoom factor
            x1, y1, x2, y2 = bounding_box
            scaled_bbox = [
                int(x1 * zoom),
                int(y1 * zoom),
                int(x2 * zoom),
                int(y2 * zoom)
            ]

            # Draw thick red rectangle
            for i in range(self.highlight_width):
                draw.rectangle(
                    [
                        (scaled_bbox[0] + i, scaled_bbox[1] + i),
                        (scaled_bbox[2] - i, scaled_bbox[3] - i)
                    ],
                    outline=self.highlight_color,
                    width=1
                )

            # Save image
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path, "PNG", optimize=True)

            doc.close()

            return output_path

        except Exception as e:
            self.logger.error(f"Error generating full page image: {e}", exc_info=True)
            return None

    def generate_chunk_images_docx(
        self,
        chunks: List[Any],
        project_id: str,
        document_id: str
    ) -> List[str]:
        """
        Generate placeholder images for DOCX chunks.

        Since DOCX doesn't have visual pages, we create placeholder images
        or skip visual grounding.

        Args:
            chunks: List of chunks
            project_id: Project ID
            document_id: Document ID

        Returns:
            List of empty strings (no images for DOCX in MVP)
        """
        # For MVP, DOCX doesn't have visual grounding
        # In future, could generate rendered page images
        return [""] * len(chunks)

    def get_image_url(self, image_path: str, base_url: str = "/api/images") -> str:
        """
        Convert relative image path to URL.

        Args:
            image_path: Relative path from data_dir
            base_url: Base URL for image serving

        Returns:
            Full URL to image
        """
        if not image_path:
            return ""

        # Convert Windows backslashes to forward slashes for URLs
        url_path = image_path.replace("\\", "/")
        return f"{base_url}/{url_path}"

    def cleanup_document_images(self, project_id: str, document_id: str) -> bool:
        """
        Delete all images for a document.

        Args:
            project_id: Project ID
            document_id: Document ID

        Returns:
            True if successful
        """
        try:
            images_dir = self.data_dir / "documents" / project_id / document_id / "chunk_images"

            if images_dir.exists():
                # Delete all images
                for img_file in images_dir.glob("*.png"):
                    img_file.unlink()

                # Remove directory
                images_dir.rmdir()

                self.logger.info(f"Cleaned up images for document {document_id}")
                return True

            return True

        except Exception as e:
            self.logger.error(f"Error cleaning up images: {e}", exc_info=True)
            return False
