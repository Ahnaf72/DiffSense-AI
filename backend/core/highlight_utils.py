"""
highlight_utils.py  ─  Extract per-sentence highlight positions from a PDF
===========================================================================

Used by the interactive viewer endpoint to tell the browser exactly which
rectangles to draw on top of the original PDF page canvas.

PyMuPDF coordinate system
──────────────────────────
  • page.rect     → Rect(0, 0, width_pts, height_pts), origin TOP-LEFT
  • page.search_for(phrase) returns Rect objects in the same space
  • 1 PDF point = 1/72 inch (default device-space unit)

In the browser (PDF.js):
  canvas_x = pdf_x * scale
  canvas_y = pdf_y * scale

No Y-axis flip needed because PyMuPDF already uses top-left origin
(matching the HTML canvas coordinate system).
"""

from __future__ import annotations
import re
import fitz          # PyMuPDF


# ── colour maps (mirror engine.py palettes exactly) ──────────────────────

# Source-identity colours (one per reference PDF, index-assigned)
_PALETTE_BG = [
    "#d4eaf5","#fbe8da","#dcedc8","#fce4ec",
    "#e8eaf6","#f3e5f5","#fbe9e7","#e0f2f1",
]
_PALETTE_FG = [
    "#1a6a8a","#c0622b","#2e7d32","#8e1c3e",
    "#1a237e","#4a148c","#bf360c","#004d40",
]

# Match-type tint offsets within each source palette row
# (0 = direct → darker, 1 = paraphrase, 2 = semantic → lightest)
_TINT_ALPHA = {"direct": 0.55, "paraphrase": 0.40, "semantic": 0.28}

# Match-type border colours (convey severity independent of source)
MATCH_TYPE_BORDER = {
    "direct":     "#c0392b",   # red
    "paraphrase": "#e67e22",   # amber
    "semantic":   "#1a6a8a",   # teal
}
MATCH_TYPE_LABEL = {
    "direct":     "Direct Match",
    "paraphrase": "Paraphrasing",
    "semantic":   "Semantic Similarity",
}


# ── helpers ────────────────────────────────────────────────────────────────

def _first_n_words(text: str, n: int) -> str:
    """Return the first n words of text joined by spaces."""
    return " ".join(text.strip().split()[:n])


def _clean_for_search(phrase: str) -> str:
    """
    Strip characters that confuse fitz.Page.search_for:
      • curly quotes → straight
      • ligatures (fi, fl, …) → plain ASCII
      • double spaces
    """
    phrase = phrase.replace("\u2018", "'").replace("\u2019", "'")
    phrase = phrase.replace("\u201c", '"').replace("\u201d", '"')
    phrase = phrase.replace("\ufb01", "fi").replace("\ufb02", "fl")
    phrase = re.sub(r"\s+", " ", phrase)
    return phrase.strip()


def _source_index(reference: str, source_list: list[str]) -> int:
    """Return the 0-based palette index for this reference filename."""
    try:
        return source_list.index(reference)
    except ValueError:
        return len(source_list) % len(_PALETTE_BG)


# ── public API ─────────────────────────────────────────────────────────────

def get_highlight_positions(
    pdf_path:       str,
    matched_chunks: list[dict],
    source_order:   list[str] | None = None,
) -> list[dict]:
    """
    Locate each matched chunk inside the original student PDF and return
    coloured highlight rectangles for every line that text spans.

    Parameters
    ----------
    pdf_path        : absolute or relative path to the student's original PDF
    matched_chunks  : list of match dicts from engine.check_plagiarism()
                      Required keys: user_chunk, match_type, reference, similarity
                      Optional key: ref_chunk (shown in the viewer tooltip)
    source_order    : ordered list of reference filenames; sets palette assignment.
                      If None, assignment is first-seen order.

    Returns
    -------
    List of highlight dicts (one dict per FOUND chunk):
    {
        "page"        : int,          # 0-based page index
        "page_width"  : float,        # PDF page width in points
        "page_height" : float,        # PDF page height in points
        "rects"       : [[x0,y0,x1,y1], …],  # one Rect per line covered
        "match_type"  : str,          # "direct" | "paraphrase" | "semantic"
        "reference"   : str,          # reference PDF filename (basename)
        "similarity"  : float,        # 0–100 similarity score
        "text"        : str,          # student chunk (first 180 chars)
        "ref_text"    : str,          # reference chunk (first 180 chars)
        "color_bg"    : str,          # CSS hex background for the highlight
        "color_border": str,          # CSS hex border (match-type severity)
        "color_fg"    : str,          # CSS hex for text/badge in the panel
        "type_label"  : str,          # human-readable match type
        "src_index"   : int,          # palette index (0-based)
    }
    """
    if not matched_chunks or not pdf_path:
        return []

    # Build source order if not provided
    if source_order is None:
        seen: list[str] = []
        for m in matched_chunks:
            ref = m.get("reference", "")
            if ref and ref not in seen:
                seen.append(ref)
        source_order = seen

    highlights: list[dict] = []

    with fitz.open(pdf_path) as doc:
        n_pages = len(doc)
        pages   = [doc[i] for i in range(n_pages)]

        for chunk in matched_chunks:
            chunk_text = chunk.get("user_chunk", "").strip()
            if not chunk_text or len(chunk_text.split()) < 5:
                continue

            match_type = chunk.get("match_type", "semantic")
            reference  = chunk.get("reference",  "")
            similarity = chunk.get("similarity", 0.0)
            ref_chunk  = chunk.get("ref_chunk",  "")
            si         = _source_index(reference, source_order)

            # Try progressively shorter search phrases until one hits.
            # Order: 12 → 8 → 6 → 4 words.  Skip phrases under 3 words.
            search_lengths = [12, 8, 6, 4]
            rects_found   = []
            found_page    = -1

            for n_words in search_lengths:
                phrase = _clean_for_search(_first_n_words(chunk_text, n_words))
                if len(phrase.split()) < 3:
                    break

                for pg_idx, page in enumerate(pages):
                    hits = page.search_for(phrase)
                    if hits:
                        rects_found = [[r.x0, r.y0, r.x1, r.y1] for r in hits]
                        found_page  = pg_idx
                        break

                if rects_found:
                    break

            if not rects_found:
                # Could not locate in PDF — skip (text layer may be absent)
                continue

            page_rect = pages[found_page].rect

            highlights.append({
                "page":         found_page,
                "page_width":   page_rect.width,
                "page_height":  page_rect.height,
                "rects":        rects_found,
                "match_type":   match_type,
                "reference":    reference,
                "similarity":   round(float(similarity), 1),
                "text":         chunk_text[:180],
                "ref_text":     ref_chunk[:180] if ref_chunk else "",
                "color_bg":     _PALETTE_BG[si % len(_PALETTE_BG)],
                "color_border": MATCH_TYPE_BORDER.get(match_type, "#888888"),
                "color_fg":     _PALETTE_FG[si % len(_PALETTE_FG)],
                "type_label":   MATCH_TYPE_LABEL.get(match_type, match_type),
                "src_index":    si,
            })

    return highlights


def get_page_dimensions(pdf_path: str) -> list[dict]:
    """
    Return width + height (in PDF points) for every page.
    The viewer uses this to create correctly-sized canvas elements
    before the highlights are drawn.
    """
    dims = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            dims.append({
                "width":  page.rect.width,
                "height": page.rect.height,
            })
    return dims