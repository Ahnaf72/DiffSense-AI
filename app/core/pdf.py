"""PDF processing module — extract text and images from PDF files.

Uses PyMuPDF (fitz) for fast, reliable extraction.

Usage:
    from app.core.pdf import extract_pdf

    result = extract_pdf(Path("uploads/user_id/doc_id_file.pdf"))
    print(result.text)          # full document text
    print(result.page_count)    # number of pages
    print(result.images[0])     # ExtractedImage dataclass
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


# ── Structured output ────────────────────────────────────────────────


@dataclass
class ExtractedImage:
    """A single extracted image from a PDF page."""
    page_number: int
    image_index: int
    width: int
    height: int
    format: str          # e.g. "png", "jpeg"
    size_bytes: int
    b64: str | None = field(default=None, repr=False)


@dataclass
class PDFExtraction:
    """Structured result from PDF extraction."""
    text: str
    page_count: int
    pages: list[str]           # text per page
    images: list[ExtractedImage]
    metadata: dict[str, str]


# ── Public API ───────────────────────────────────────────────────────


def extract_pdf(
    path: Path,
    *,
    extract_images: bool = True,
    image_max_bytes: int = 5 * 1024 * 1024,
    image_include_b64: bool = False,
) -> PDFExtraction:
    """Extract text and optionally images from a PDF file.

    Args:
        path: Path to the PDF file.
        extract_images: Whether to extract embedded images.
        image_max_bytes: Skip images larger than this (default 5 MB).
        image_include_b64: Include base64-encoded image data in output.

    Returns:
        PDFExtraction dataclass with text, pages, images, metadata.
    """
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    doc = fitz.open(str(path))
    try:
        pages_text: list[str] = []
        all_images: list[ExtractedImage] = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # ── Text extraction ──
            text = page.get_text("text")
            pages_text.append(text)

            # ── Image extraction ──
            if extract_images:
                img_list = page.get_images(full=True)
                for img_idx, img_info in enumerate(img_list):
                    xref = img_info[0]
                    try:
                        base_image = doc.extract_image(xref)
                    except Exception:
                        logger.warning("Failed to extract image xref=%d on page %d", xref, page_num)
                        continue

                    if not base_image:
                        continue

                    img_bytes = base_image.get("image", b"")
                    if len(img_bytes) > image_max_bytes:
                        logger.debug(
                            "Skipping large image xref=%d (%d bytes)", xref, len(img_bytes)
                        )
                        continue

                    extracted = ExtractedImage(
                        page_number=page_num + 1,
                        image_index=img_idx,
                        width=base_image.get("width", 0),
                        height=base_image.get("height", 0),
                        format=base_image.get("ext", "unknown"),
                        size_bytes=len(img_bytes),
                        b64=base64.b64encode(img_bytes).decode() if image_include_b64 else None,
                    )
                    all_images.append(extracted)

        # ── Metadata ──
        meta = {}
        for key in ("title", "author", "subject", "creator", "producer", "creationDate", "modDate"):
            val = doc.metadata.get(key)
            if val:
                meta[key] = val

        full_text = "\n\n".join(pages_text)

        return PDFExtraction(
            text=full_text,
            page_count=len(doc),
            pages=pages_text,
            images=all_images,
            metadata=meta,
        )
    finally:
        doc.close()


def extract_text_only(path: Path) -> str:
    """Convenience: extract just the text from a PDF."""
    return extract_pdf(path, extract_images=False).text


def page_count(path: Path) -> int:
    """Convenience: return number of pages without full extraction."""
    doc = fitz.open(str(path))
    try:
        return len(doc)
    finally:
        doc.close()
