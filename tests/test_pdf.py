"""Tests for the PDF processing module."""

import os
from pathlib import Path

import fitz

from app.core.pdf import extract_pdf, extract_text_only, page_count

_TEST_PDF = Path("_test_pdf_unit.pdf")


def _make_pdf(num_pages: int = 3, lines_per_page: int = 5) -> Path:
    """Create a temp PDF for testing in the project dir."""
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i+1}", fontsize=16)
        for j in range(lines_per_page):
            page.insert_text((72, 110 + j * 18), f"Line {j+1}: test content")
    doc.save(str(_TEST_PDF))
    doc.close()
    return _TEST_PDF


class TestExtractPdf:
    def test_text_extraction(self):
        path = _make_pdf(num_pages=2)
        try:
            result = extract_pdf(path, extract_images=False)
            assert result.page_count == 2
            assert "Page 1" in result.text
            assert "Page 2" in result.text
            assert len(result.pages) == 2
            assert result.images == []
        finally:
            path.unlink(missing_ok=True)

    def test_extract_text_only(self):
        path = _make_pdf(num_pages=1)
        try:
            text = extract_text_only(path)
            assert "Page 1" in text
        finally:
            path.unlink(missing_ok=True)

    def test_page_count(self):
        path = _make_pdf(num_pages=4)
        try:
            assert page_count(path) == 4
        finally:
            path.unlink(missing_ok=True)

    def test_metadata(self):
        path = _make_pdf()
        try:
            result = extract_pdf(path, extract_images=False)
            assert isinstance(result.metadata, dict)
        finally:
            path.unlink(missing_ok=True)

    def test_file_not_found(self):
        try:
            extract_pdf(Path("/nonexistent/file.pdf"))
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass
