"""
plagiarism.py  ─  Core plagiarism detection engine
====================================================

check_plagiarism(student_pdf, reference_pdfs)
    └─ returns list of per-reference result dicts (see docstring)

Three-tier detection per sentence
──────────────────────────────────
  direct      verbatim or near-verbatim copy   (Jaccard ≥ 0.70 or cos ≥ 0.95)
  paraphrase  same meaning, different wording  (cos ≥ 0.82, Jaccard < 0.70)
  semantic    topically related content        (0.65 ≤ cos < 0.82)

Fixes vs original
──────────────────
  • Sentence-level granularity instead of 300-word chunks
  • Jaccard overlap added for direct-match detection
  • Corrected image-loop IndentationError (extra space before break)
  • image_similarity no longer re-defined locally; uses pdf_utils version
  • overall_similarity denominator is uniform (student sentence count)
  • Table/image matches are reported separately, not mixed into the ratio
  • Full per-sentence detail returned so the report can highlight each one
"""

from backend.pdf_utils import extract_text, extract_tables, extract_images
from backend.pdf_utils import image_similarity as _image_sim
from backend.nlp_utils import (
    get_embeddings,
    jaccard_similarity,
    split_sentences,
    classify_match,
    remove_references,
)
import numpy as np


# ══════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════

def check_plagiarism(student_pdf: str, reference_pdfs: list[str]) -> list[dict]:
    """
    Compare a student PDF against every reference PDF.

    Returns
    -------
    list of dicts, one per reference:
    {
        "reference":          str,    # path to the reference PDF
        "overall_similarity": float,  # 0–100, based on sentence matches
        "direct_percent":     float,  # % of student sentences – direct match
        "paraphrase_percent": float,  # % of student sentences – paraphrase
        "semantic_percent":   float,  # % of student sentences – semantic
        "sentence_matches": [
            {
                "student_sentence": str,
                "matched_sentence": str,
                "match_type":       "direct" | "paraphrase" | "semantic",
                "cosine":           float,   # embedding cosine similarity
                "jaccard":          float,   # word-overlap Jaccard index
            },
            ...
        ],
        "table_matches": int,   # number of matching tables
        "image_matches": int,   # number of matching images
    }
    """
    # ── Prepare student content ───────────────────────────────────────────
    student_raw    = extract_text(student_pdf)
    student_clean  = remove_references(student_raw)
    student_sents  = split_sentences(student_clean)
    student_tables = extract_tables(student_pdf)
    student_images = extract_images(student_pdf)

    if not student_sents:
        return []

    # Batch-encode all student sentences once
    student_embs = get_embeddings(student_sents)   # (N, 384) L2-normalised

    results = []

    for ref_pdf in reference_pdfs:

        # ── Prepare reference content ─────────────────────────────────────
        ref_raw    = extract_text(ref_pdf)
        ref_clean  = remove_references(ref_raw)
        ref_sents  = split_sentences(ref_clean)
        ref_tables = extract_tables(ref_pdf)
        ref_images = extract_images(ref_pdf)

        if not ref_sents:
            results.append(_empty_result(ref_pdf))
            continue

        # Batch-encode reference sentences
        ref_embs = get_embeddings(ref_sents)       # (M, 384)

        # ── Sentence-level comparison ─────────────────────────────────────
        # Full cosine similarity matrix  (N × M)
        # Because embeddings are L2-normalised: cosine == dot product
        cosine_matrix = student_embs @ ref_embs.T  # (N, M)

        sentence_matches = []
        type_counts      = {"direct": 0, "paraphrase": 0, "semantic": 0}

        for i, s_sent in enumerate(student_sents):
            # Find the single most similar reference sentence
            best_j      = int(np.argmax(cosine_matrix[i]))
            best_cosine = float(cosine_matrix[i, best_j])
            best_r_sent = ref_sents[best_j]

            # Word-overlap check (cheap, no model needed)
            best_jaccard = jaccard_similarity(s_sent, best_r_sent)

            match_type = classify_match(best_cosine, best_jaccard)

            if match_type is None:
                continue

            type_counts[match_type] += 1
            sentence_matches.append({
                "student_sentence": s_sent,
                "matched_sentence": best_r_sent,
                "match_type":       match_type,
                "cosine":           round(best_cosine,  4),
                "jaccard":          round(best_jaccard, 4),
            })

        # ── Table comparison ──────────────────────────────────────────────
        # Use Jaccard on stringified table rows (fast, no embedding needed)
        table_matches = 0
        for st in student_tables:
            for rt in ref_tables:
                if jaccard_similarity(str(st), str(rt)) > 0.75:
                    table_matches += 1
                    break          # ← correct indentation (was broken before)

        # ── Image comparison ──────────────────────────────────────────────
        # Lower MSE means more similar; threshold empirically set at 1 000
        image_matches = 0
        for si in student_images:
            for ri in ref_images:
                try:
                    if _image_sim(si, ri) < 1000:
                        image_matches += 1
                        break      # ← correct indentation (was broken before)
                except Exception:
                    continue       # skip unreadable / corrupt images

        # ── Overall similarity ────────────────────────────────────────────
        # Denominator = number of student sentences (uniform, reproducible)
        # Table and image matches are reported separately (not folded in)
        n_sents  = len(student_sents)
        n_matched = sum(type_counts.values())
        overall   = (n_matched / n_sents * 100) if n_sents else 0.0

        results.append({
            "reference":           ref_pdf,
            "similarity":          round(overall, 2),
            "direct_percent":      round(type_counts["direct"]     / n_sents * 100, 2),
            "paraphrase_percent":  round(type_counts["paraphrase"] / n_sents * 100, 2),
            "semantic_percent":    round(type_counts["semantic"]   / n_sents * 100, 2),
            "_st": {
                "display_pct": f"{round(overall, 1)}%",
                "d": f"{round(type_counts['direct'] / n_sents * 100, 1)}%",
                "p": f"{round(type_counts['paraphrase'] / n_sents * 100, 1)}%",
                "s": f"{round(type_counts['semantic'] / n_sents * 100, 1)}%"
            },
            "sentence_matches":    sentence_matches,
            "table_matches":       table_matches,
            "image_matches":       image_matches,
        })

    return results


# ══════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _empty_result(ref_pdf: str) -> dict:
    return {
        "reference":          ref_pdf,
        "overall_similarity": 0.0,
        "direct_percent":     0.0,
        "paraphrase_percent": 0.0,
        "semantic_percent":   0.0,
        "sentence_matches":   [],
        "table_matches":      0,
        "image_matches":      0,
    }