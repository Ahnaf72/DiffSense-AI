"""
pdf_utils.py  ─  PDF extraction helpers
========================================
• extract_text(pdf_path)    → plain text string
• extract_tables(pdf_path)  → list of tables (each table = list of rows)
• extract_images(pdf_path)  → list of raw image bytes
• image_similarity(a, b)    → mean-squared pixel error (lower = more similar)
"""

import fitz          # PyMuPDF
import pdfplumber
import cv2
import numpy as np


# ──────────────────────────────────────────────────────────────────────────
# TEXT
# ──────────────────────────────────────────────────────────────────────────
def extract_text(pdf_path: str) -> str:
    """Extract all text from every page of a PDF."""
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text()
    return text


# ──────────────────────────────────────────────────────────────────────────
# TABLES
# ──────────────────────────────────────────────────────────────────────────
def extract_tables(pdf_path: str) -> list:
    """
    Extract all tables from a PDF using pdfplumber.
    Returns a flat list of tables; each table is a list of rows.
    """
    tables = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_tables = page.extract_tables()
            if page_tables:
                tables.extend(page_tables)
    return tables


# ──────────────────────────────────────────────────────────────────────────
# IMAGES / FIGURES
# ──────────────────────────────────────────────────────────────────────────
def extract_images(pdf_path: str) -> list[bytes]:
    """
    Extract raw image bytes from every page of a PDF.
    Returns a list of bytes objects (one per image).
    """
    images = []
    with fitz.open(pdf_path) as doc:
        for page_index in range(len(doc)):
            for img_info in doc.get_page_images(page_index):
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                images.append(base_image["image"])
    return images


def image_similarity(img_bytes_1: bytes, img_bytes_2: bytes) -> float:
    """
    Compute pixel-level Mean Squared Error between two images.
    Lower value → more similar (0 = identical).
    Both images are resized to 100×100 before comparison.
    """
    arr1 = np.frombuffer(img_bytes_1, dtype=np.uint8)
    arr2 = np.frombuffer(img_bytes_2, dtype=np.uint8)

    img1 = cv2.imdecode(arr1, cv2.IMREAD_COLOR)
    img2 = cv2.imdecode(arr2, cv2.IMREAD_COLOR)

    # If decoding failed, treat as completely different
    if img1 is None or img2 is None:
        return float("inf")

    img1 = cv2.resize(img1, (100, 100))
    img2 = cv2.resize(img2, (100, 100))

    return float(np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2))