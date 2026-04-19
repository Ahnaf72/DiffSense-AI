"""
report_generator.py
====================
NOTE: For the main /run_check flow you do NOT need this file at all —
the engine builds the report itself inside run_engine().
See main_patch.py.

This file is kept for any caller that explicitly wants to regenerate
a report from saved results. It now passes all four engine outputs
(results, details, user_chunks, uncited_mask) to build_turnitin_pdf
so the word-level highlighting works correctly.
"""

from backend.report_builder import build_turnitin_pdf


def generate_report(
    output_path:      str,
    results:          list,
    student_name:     str  = "student_document.pdf",
    student_pdf_path: str  = "",
    details:          list | None = None,
    user_chunks:      list | None = None,
    uncited_mask:     list | None = None,
) -> None:
    """
    Generate a Turnitin-style PDF report.

    Parameters
    ----------
    output_path      : destination file path
    results          : list of result dicts from check_plagiarism()
                       Keys: reference, similarity, match_types, uncited_total,
                             table_matches, image_matches
    student_name     : display name shown in the report header
    student_pdf_path : path to the original student PDF (needed for highlighting)
    details          : list of matched chunk detail dicts from check_plagiarism()
                       Keys: user_chunk_idx, user_chunk, ref_chunk,
                             match_type, similarity, reference
    user_chunks      : all text chunks from the student PDF
    uncited_mask     : bool list — which chunks are uncited
    """
    build_turnitin_pdf(
        student_pdf_name=student_name,
        student_pdf_path=student_pdf_path,
        all_results=results,
        output_path=output_path,
        all_details=details,
        user_chunks=user_chunks,
        uncited_mask=uncited_mask,
    )