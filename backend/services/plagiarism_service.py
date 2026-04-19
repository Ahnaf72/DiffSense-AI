"""
plagiarism_service.py  ─  Turnitin-style plagiarism detection service
======================================================================
Orchestrates the full plagiarism check pipeline:
  1. Collect reference PDFs
  2. Run AI detection engine (sentence-level, table, image)
  3. Generate colour-coded Turnitin-style PDF report
  4. Persist results to the database
  5. Return structured results for the frontend

This is the primary service called by the API routes.
"""

import os
from typing import Optional

from backend.db.supabase_client import db
from backend.db.user_db import save_result, get_results, get_uploads
from backend.config import config


def get_reference_pdfs() -> list[str]:
    """Return absolute paths to all reference PDFs."""
    ref_dir = config.REFERENCE_DIR
    if not os.path.isdir(ref_dir):
        return []
    return sorted(
        os.path.join(ref_dir, f)
        for f in os.listdir(ref_dir)
        if f.lower().endswith(".pdf")
    )


def run_plagiarism_check(username: str, role: str, filename: str) -> dict:
    """
    Run a full plagiarism check on an uploaded file.

    Returns a dict with:
        success:            bool
        result_url:         str   - URL to the generated report PDF
        overall_similarity: float - 0-100 overall score
        per_reference:      list  - breakdown per reference PDF
        highlights:         list  - highlight data for interactive viewer
        page_dims:          list  - page dimensions for viewer
    """
    from backend.core.engine import run_engine

    # Resolve the uploaded file path
    if role == "student":
        pdf_path = os.path.join(config.STUDENT_ROOT, username, filename)
    elif role == "teacher":
        pdf_path = os.path.join(config.TEACHER_ROOT, username, filename)
    else:
        return {"success": False, "error": "Admins cannot run checks"}

    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"File '{filename}' not found"}

    # Get reference PDFs
    reference_pdfs = get_reference_pdfs()
    if not reference_pdfs:
        return {"success": False, "error": "No reference PDFs available. Ask admin to upload some."}

    try:
        result_pdf_path, results, details = run_engine(username, role, pdf_path)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Engine error: {e}"}

    # Build the result URL
    result_url = "/" + result_pdf_path.replace("\\", "/")

    # Overall similarity = max across all references
    overall = max((r.get("similarity", 0) for r in results), default=0)

    # Per-reference breakdown (Turnitin-style)
    per_reference = []
    for r in results:
        uncited_total = max(r.get("uncited_total", 1), 1)
        mt = r.get("match_types", {})
        per_reference.append({
            "reference":          r.get("reference", ""),
            "similarity":         r.get("similarity", 0),
            "direct_percent":     round(mt.get("direct", 0) / uncited_total * 100, 1),
            "paraphrase_percent": round(mt.get("paraphrase", 0) / uncited_total * 100, 1),
            "semantic_percent":   round(mt.get("semantic", 0) / uncited_total * 100, 1),
            "table_matches":      r.get("table_matches", 0),
            "image_matches":      r.get("image_matches", 0),
        })

    # Persist to database
    try:
        save_result(username, role, filename, result_pdf_path, results)
    except Exception as e:
        print(f"[WARN] Failed to save results to DB: {e}")

    return {
        "success":            True,
        "result_url":         result_url,
        "overall_similarity": round(overall, 2),
        "per_reference":      per_reference,
    }


def get_viewer_data(username: str, role: str, filename: str) -> dict:
    """
    Return all data needed for the interactive Turnitin-style viewer:
      - pdf_url:      URL to stream the original student PDF
      - highlights:   per-chunk coloured rectangles
      - page_dims:    width + height of every page
      - sources:      per-reference summary stats + palette colours
      - overall:      max similarity across all references
    """
    from backend.core.engine import check_plagiarism, REFERENCE_DIR
    from backend.core.highlight_utils import get_highlight_positions, get_page_dimensions

    # Resolve PDF path
    if role == "student":
        pdf_path = os.path.join(config.STUDENT_ROOT, username, filename)
    elif role == "teacher":
        pdf_path = os.path.join(config.TEACHER_ROOT, username, filename)
    else:
        return {"success": False, "error": "Admins cannot use viewer"}

    if not os.path.exists(pdf_path):
        return {"success": False, "error": f"File not found"}

    # Collect reference PDFs
    reference_pdfs = get_reference_pdfs()
    if not reference_pdfs:
        return {"success": False, "error": "No reference PDFs available"}

    # Run detection
    try:
        results, details, user_chunks, uncited_mask = check_plagiarism(
            pdf_path, reference_pdfs
        )
    except Exception as exc:
        return {"success": False, "error": f"Engine error: {exc}"}

    # Build source order (descending by similarity)
    matched = [r for r in results if sum(r.get("match_types", {}).values()) > 0]
    matched.sort(key=lambda r: r.get("similarity", 0), reverse=True)
    source_order = [r["reference"] for r in matched]

    # Highlight positions
    try:
        highlights = get_highlight_positions(pdf_path, details, source_order)
    except Exception:
        highlights = []

    # Page dimensions
    try:
        page_dims = get_page_dimensions(pdf_path)
    except Exception:
        page_dims = []

    # Source summary rows
    _PALETTE_FG = [
        "#1a6a8a", "#c0622b", "#2e7d32", "#8e1c3e",
        "#1a237e", "#4a148c", "#bf360c", "#004d40",
    ]
    _PALETTE_BG = [
        "#d4eaf5", "#fbe8da", "#dcedc8", "#fce4ec",
        "#e8eaf6", "#f3e5f5", "#fbe9e7", "#e0f2f1",
    ]

    uncited_total = max(sum(uncited_mask), 1)
    sources = []
    for i, r in enumerate(matched):
        mt = r.get("match_types", {})
        sources.append({
            "name":       r["reference"],
            "similarity": r.get("similarity", 0),
            "direct":     round(mt.get("direct", 0) / uncited_total * 100, 1),
            "paraphrase": round(mt.get("paraphrase", 0) / uncited_total * 100, 1),
            "semantic":   round(mt.get("semantic", 0) / uncited_total * 100, 1),
            "table_hits": r.get("table_matches", 0),
            "image_hits": r.get("image_matches", 0),
            "color_fg":   _PALETTE_FG[i % len(_PALETTE_FG)],
            "color_bg":   _PALETTE_BG[i % len(_PALETTE_BG)],
        })

    overall = max((r.get("similarity", 0) for r in results), default=0.0)

    pdf_url = (
        f"/student_files/{username}/{filename}"
        if role == "student"
        else f"/teacher_files/{username}/{filename}"
    )

    return {
        "success":      True,
        "filename":     filename,
        "pdf_url":      pdf_url,
        "overall":      round(overall, 1),
        "highlights":   highlights,
        "page_dims":    page_dims,
        "sources":      sources,
        "total_chunks": len(user_chunks),
        "uncited":      int(uncited_total),
    }


def get_dashboard_stats() -> dict:
    """Return admin dashboard statistics."""
    ref_count = db.count_reference_pdfs()
    total_users = db.count_users()

    teacher_uploads = 0
    student_uploads = 0

    teachers = db.list_users(role="teacher")
    for u in teachers:
        teacher_uploads += len(get_uploads(u["username"], "teacher"))

    students = db.list_users(role="student")
    for u in students:
        student_uploads += len(get_uploads(u["username"], "student"))

    return {
        "total_users":      total_users,
        "reference_pdfs":   ref_count,
        "teacher_uploads":  teacher_uploads,
        "student_uploads":  student_uploads,
        "comparisons":      0,
    }
