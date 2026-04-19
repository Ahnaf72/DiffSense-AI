"""
engine_offline.py  -  AI Plagiarism Detection Engine  (Offline Edition)

Key upgrades over v5:
  1. WORD-LEVEL sliding window chunks (size=30, step=5) instead of paragraph-
     locked 50-word windows → tighter boundary detection when multiple reference
     PDFs are jumbled together; each chunk overlaps heavily so no match can slip
     through a boundary gap.
  2. OFFLINE AI model: sentence-transformers `all-MiniLM-L6-v2`
       • 384-dim, ~80 MB, runs 100 % locally (no API key, no internet)
       • ~5-10× faster than larger models on CPU; GPU-accelerated automatically
       • Identical classification logic, thresholds, and report layout as v5
  3. TABLE matching: embedding cosine similarity (same as v5, threshold 0.95)
  4. IMAGE matching: pixel-MAE on resized thumbnails (same as v5, threshold 1000)

Layout mirrors Turnitin exactly (unchanged from v5):
  Page 1  : Match Overview
  Page 2+ : Original PDF with highlight annotations
  Last    : Summary Analysis table
"""

import os, re, io, hashlib, pickle, logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import faiss
import fitz                                  # PyMuPDF
from rank_bm25 import BM25Okapi

# ── Offline embedding model via nlp_utils (unified entry point) ────────────────
# Uses nlp_utils.get_embeddings() which handles FastEmbed / ST fallback.
from typing import Optional

_degraded_mode = False  # Global flag set at check_plagiarism() entry


def get_embeddings(texts: list[str]) -> Optional[np.ndarray]:
    """
    Return float32 embeddings for a list of texts (offline, fast).
    Returns None if model unavailable (triggers BM25-only mode).
    Delegates to nlp_utils.get_embeddings which handles model loading.
    """
    from backend.core.nlp_utils import get_embeddings as _get_embs
    result = _get_embs(texts, batch_size=64)
    if result is None:
        return None
    # nlp_utils already L2-normalises, but engine.py callers expect raw
    # normalised vectors too, so just return as-is
    return result

# ── Import the rest from your existing backend helpers ───────────────────────
from backend.core.nlp_utils import remove_references
from backend.core.pdf_utils import extract_text, extract_tables, extract_images, image_similarity
from backend.db.user_db   import save_result

from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, FrameBreak,
    Paragraph, Spacer, Table, TableStyle, HRFlowable,
    NextPageTemplate, PageBreak,
)
from reportlab.lib           import colors
from reportlab.lib.styles    import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.units     import cm
from reportlab.lib.enums     import TA_LEFT, TA_CENTER, TA_RIGHT

# ---------------------------------------------------------------------------
# Diagnostic logger
# ---------------------------------------------------------------------------
os.makedirs("backend/data", exist_ok=True)
_diag_log = logging.getLogger("sim_diagnostics_offline")
_diag_log.setLevel(logging.DEBUG)
if not _diag_log.handlers:
    _fh = logging.FileHandler("backend/data/sim_diagnostics_offline.log",
                               mode="w", encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(message)s"))
    _diag_log.addHandler(_fh)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REFERENCE_DIR   = "backend/data/reference_pdfs"
RESULT_ROOT     = "data/result_pdfs"
EMBED_CACHE_DIR = "backend/data/embed_cache_offline"

# ── Chunking — WORD-LEVEL sliding window ────────────────────────────────────
#   Smaller chunks + heavy overlap ensure that text straddling the boundary
#   between two different reference PDFs is always captured cleanly.
CHUNK_WORDS     = 30          # window width in words  (was 50, paragraph-locked)
CHUNK_STEP      = 5           # slide step in words    (was 25, paragraph-locked)
MIN_CHUNK_WORDS = 8           # discard windows shorter than this

# ── Classification thresholds (tuned for MiniLM-L6-v2) ─────────────────────
DIRECT_SEM_SIM        = 0.97   # near-identical → direct
DIRECT_WORD_OVERLAP   = 0.60   # ≥60% word overlap → direct (+ sem gate)
DIRECT_COMBINED_OV    = 0.60   # sem ≥ PARAPHRASE_SEM + ov ≥ this → direct
PARAPHRASE_SEM_SIM    = 0.82
PARAPHRASE_HIGH_SEM   = 0.85
PARAPHRASE_WORD_FLOOR = 0.22
MIN_CONTENT_WORDS     = 3
SEMANTIC_SEM_SIM      = 0.73
RELATIVE_MARGIN       = 0.08

TABLE_SIM_THRESHOLD   = 0.95
IMAGE_DIFF_THRESHOLD  = 1000
BM25_HIGH_THRESHOLD   = 2.0
BM25_TOP_K            = 5
MAX_WORKERS           = 4
NEURAL_BATCH_SIZE     = 64    # larger batches — MiniLM is fast

_CITED = re.compile(
    r"(\([A-Z][a-zA-Z]+(?: et al\.)?[,\s]+\d{4}\))"
    r"|(\[\d+(?:[,\-]\d+)*\])"
    r"|(ibid\.?|op\.\s?cit\.?)",
    re.IGNORECASE,
)

_STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "this","that","these","those","it","its","they","their","we","our",
    "as","if","then","than","so","yet","both","each","more","also","not",
    "no","nor","about","after","before","between","into","through","during",
    "which","who","what","when","where","how","all","any","some","such",
}

# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _l2_normalize(embs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    return embs / norms

def _tokenize(text):
    return re.sub(r"[^\w\s]", "", text.lower()).split()

def _split_chunks(text: str,
                  chunk_words: int = CHUNK_WORDS,
                  step: int        = CHUNK_STEP,
                  min_words: int   = MIN_CHUNK_WORDS) -> list[str]:
    """
    Word-level sliding-window chunker.

    Unlike the paragraph-aware approach in v5 this function slides a fixed
    window of `chunk_words` words across the ENTIRE text in steps of `step`
    words.  Overlapping windows mean every possible phrase is covered and
    boundary chunks (where one reference ends and another begins) appear as
    partial matches rather than missed matches.
    """
    words = text.split()
    chunks = []
    for i in range(0, max(len(words) - min_words + 1, 1), step):
        w = words[i: i + chunk_words]
        if len(w) >= min_words:
            chunks.append(" ".join(w))
    return chunks

def _word_overlap(a: str, b: str) -> float:
    a_clean = re.sub(r"[^\w\s]", "", a.replace("-", " ").lower())
    b_clean = re.sub(r"[^\w\s]", "", b.replace("-", " ").lower())
    sa = set(a_clean.split())
    sb = set(b_clean.split())
    return len(sa & sb) / len(sa) if sa else 0.0

def _content_word_overlap(a: str, b: str) -> int:
    a_clean = re.sub(r"[^\w\s]", "", a.replace("-", " ").lower())
    b_clean = re.sub(r"[^\w\s]", "", b.replace("-", " ").lower())
    sa = {w for w in a_clean.split() if w not in _STOPWORDS}
    sb = {w for w in b_clean.split() if w not in _STOPWORDS}
    return len(sa & sb)

def _is_cited(chunk: str) -> bool:
    return bool(_CITED.search(chunk))

def _classify(sem, overlap, content_overlap, mean_sim, user_chunk_text):
    chunk_length = len(user_chunk_text.split())
    if chunk_length < 15:
        required_content_words = 1
    elif chunk_length < 25:
        required_content_words = 2
    else:
        required_content_words = MIN_CONTENT_WORDS

    # DIRECT
    if sem >= DIRECT_SEM_SIM:
        return "direct"
    if overlap >= DIRECT_WORD_OVERLAP and sem >= SEMANTIC_SEM_SIM:
        return "direct"
    if sem >= PARAPHRASE_SEM_SIM and overlap >= DIRECT_COMBINED_OV:
        return "direct"

    # PARAPHRASE
    if (PARAPHRASE_SEM_SIM <= sem < DIRECT_SEM_SIM
            and overlap >= PARAPHRASE_WORD_FLOOR
            and overlap < DIRECT_COMBINED_OV
            and content_overlap >= required_content_words):
        return "paraphrase"
    if (PARAPHRASE_HIGH_SEM <= sem < DIRECT_SEM_SIM
            and overlap < DIRECT_COMBINED_OV
            and content_overlap >= required_content_words):
        return "paraphrase"

    # SEMANTIC
    relative_threshold = min(mean_sim + RELATIVE_MARGIN, 0.77)
    if (sem >= SEMANTIC_SEM_SIM
            and sem >= relative_threshold
            and overlap < DIRECT_WORD_OVERLAP):
        return "semantic"

    return "none"

# ---------------------------------------------------------------------------
# Cache  (keyed on model name so upgrading the model invalidates old caches)
# ---------------------------------------------------------------------------
CACHE_VERSION = "v1_minilm_wordslide"

def _cache_path(pdf_path):
    stat = os.stat(pdf_path)
    key  = f"{pdf_path}:{stat.st_mtime}:{stat.st_size}:{CACHE_VERSION}"
    h    = hashlib.md5(key.encode()).hexdigest()
    os.makedirs(EMBED_CACHE_DIR, exist_ok=True)
    return os.path.join(EMBED_CACHE_DIR, f"{h}.pkl")

def _load_ref_data(ref_path):
    cp = _cache_path(ref_path)
    if os.path.exists(cp):
        try:
            with open(cp, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, tuple) and len(data) == 4 and data[0] == CACHE_VERSION:
                _, chunks, bm25, index = data
                return chunks, bm25, index
        except Exception:
            pass
        os.remove(cp)

    ref_text  = remove_references(extract_text(ref_path))
    chunks    = _split_chunks(ref_text)
    tokenized = [_tokenize(c) for c in chunks]
    bm25      = BM25Okapi(tokenized) if tokenized else None
    if chunks:
        embs  = _l2_normalize(get_embeddings(chunks))
        index = faiss.IndexFlatIP(embs.shape[1])
        index.add(embs)
    else:
        index = faiss.IndexFlatIP(384)

    with open(cp, "wb") as f:
        pickle.dump((CACHE_VERSION, chunks, bm25, index), f)
    return chunks, bm25, index

# ---------------------------------------------------------------------------
# Per-reference worker
# ---------------------------------------------------------------------------

def _check_one_reference(ref_path, user_chunks, uncited_mask, user_tables, user_images):
    ref_name                     = os.path.basename(ref_path)
    ref_chunks, bm25, faiss_idx  = _load_ref_data(ref_path)
    ref_tables                   = extract_tables(ref_path)
    ref_images                   = extract_images(ref_path)

    uncited_total = max(sum(uncited_mask), 1)
    matched       = []
    type_counts   = {"direct": 0, "paraphrase": 0, "semantic": 0}

    if ref_chunks and bm25:
        uncited_indices = [ui for ui, uc in enumerate(user_chunks) if uncited_mask[ui]]
        uncited_texts   = [user_chunks[ui] for ui in uncited_indices]

        if uncited_texts:
            # ── DEGRADED MODE: BM25-only matching ─────────────────────────────
            if _degraded_mode:
                _diag_log.debug(f"[DEGRADED] Processing {ref_name} with BM25-only")
                _PRIORITY = {"direct": 3, "paraphrase": 2, "semantic": 1}
                best_match_per_chunk: dict[int, dict] = {}

                for ui, uc in zip(uncited_indices, uncited_texts):
                    tokens = _tokenize(uc)
                    bm25_sc = bm25.get_scores(tokens)
                    bm25_top_idx = np.argsort(bm25_sc)[-BM25_TOP_K:]

                    for ri in bm25_top_idx:
                        if ri >= len(ref_chunks):
                            continue
                        rc = ref_chunks[ri]
                        overlap = _word_overlap(uc, rc)

                        # In degraded mode: only detect direct matches (>=75% overlap)
                        if overlap >= DIRECT_WORD_OVERLAP:
                            mt = "direct"
                            # Use BM25 score as pseudo-similarity (normalize to 0-1)
                            pseudo_sim = min(bm25_sc[ri] / 10.0, 1.0)

                            prev = best_match_per_chunk.get(ui)
                            if prev is None or _PRIORITY[mt] > _PRIORITY.get(prev["match_type"], 0):
                                best_match_per_chunk[ui] = {
                                    "user_chunk_idx": ui,
                                    "user_chunk": uc,
                                    "ref_chunk": rc,
                                    "match_type": mt,
                                    "similarity": pseudo_sim,
                                    "word_overlap": overlap,
                                    "source": ref_name,
                                }

                for ui, m in best_match_per_chunk.items():
                    matched.append(m)
                    type_counts[m["match_type"]] += 1

            # ── NORMAL MODE: Full neural + BM25 matching ─────────────────────
            else:
                user_embs_raw = get_embeddings(uncited_texts)
                if user_embs_raw is None:
                    # Embeddings failed mid-run - skip this reference
                    _diag_log.warning(f"Embeddings failed for {ref_name} - skipping")
                else:
                    user_embs = _l2_normalize(user_embs_raw)

                    # ── Candidate gathering: BM25 union FAISS ─────────────────
                    neural_queue = []
                    for idx_in_batch, (ui, uc) in enumerate(zip(uncited_indices, uncited_texts)):
                        ue = user_embs[idx_in_batch]

                        tokens    = _tokenize(uc)
                        bm25_sc   = bm25.get_scores(tokens)
                        bm25_top  = set(np.argsort(bm25_sc)[-BM25_TOP_K:].tolist())

                        query         = ue.reshape(1, -1)
                        _, faiss_top  = faiss_idx.search(query, BM25_TOP_K)
                        faiss_top_set = set(faiss_top[0].tolist())

                        all_cand_idx = (bm25_top | faiss_top_set) - {-1}
                        candidates   = [ref_chunks[i] for i in sorted(all_cand_idx)
                                        if i < len(ref_chunks)]
                        if candidates:
                            neural_queue.append((ui, uc, ue, candidates))

                    if neural_queue:
                        # Embed all unique candidate texts once
                        all_cand_texts = []
                        for _, _, _, cands in neural_queue:
                            all_cand_texts.extend(cands)
                        unique_cand_texts = list(dict.fromkeys(all_cand_texts))
                        cand_emb_map = {}
                        for bs in range(0, len(unique_cand_texts), NEURAL_BATCH_SIZE):
                            batch  = unique_cand_texts[bs: bs + NEURAL_BATCH_SIZE]
                            embs_raw = get_embeddings(batch)
                            if embs_raw is not None:
                                embs = _l2_normalize(embs_raw)
                                for t, e in zip(batch, embs):
                                    cand_emb_map[t] = e

                        if cand_emb_map:
                            all_best_sims = []
                            for ui, uc, ue, candidates in neural_queue:
                                valid_cands = [c for c in candidates if c in cand_emb_map]
                                if not valid_cands:
                                    continue
                                cand_embs = np.stack([cand_emb_map[c] for c in valid_cands])
                                sims      = cand_embs @ ue
                                all_best_sims.append(float(np.max(sims)))

                            mean_sim = float(np.mean(all_best_sims)) if all_best_sims else 0.0
                            p25      = float(np.percentile(all_best_sims, 25)) if all_best_sims else 0.0
                            p75      = float(np.percentile(all_best_sims, 75)) if all_best_sims else 0.0

                            _diag_log.debug("=" * 60)
                            _diag_log.debug(f"REF: {ref_name}")
                            _diag_log.debug(f"  uncited chunks : {uncited_total}")
                            _diag_log.debug(f"  neural queue   : {len(neural_queue)}")
                            _diag_log.debug(f"  cosine mean    : {mean_sim:.4f}")
                            _diag_log.debug(f"  cosine p25/p75 : {p25:.4f} / {p75:.4f}")

                            # ── Classify each user chunk ─────────────────────────
                            _PRIORITY = {"direct": 3, "paraphrase": 2, "semantic": 1}
                            best_match_per_chunk: dict[int, dict] = {}

                            for ui, uc, ue, candidates in neural_queue:
                                valid_cands = [c for c in candidates if c in cand_emb_map]
                                if not valid_cands:
                                    continue
                                cand_embs = np.stack([cand_emb_map[c] for c in valid_cands])
                                sims      = cand_embs @ ue
                                best_i    = int(np.argmax(sims))
                                best_sim  = float(sims[best_i])
                                best_rc   = valid_cands[best_i]
                                overlap   = _word_overlap(uc, best_rc)
                                co        = _content_word_overlap(uc, best_rc)
                                mt        = _classify(best_sim, overlap, co, mean_sim, uc)
                                if mt == "none":
                                    continue
                                prev = best_match_per_chunk.get(ui)
                                if prev is None or _PRIORITY[mt] > _PRIORITY[prev["match_type"]]:
                                    best_match_per_chunk[ui] = {
                                        "user_chunk_idx": ui,
                                        "user_chunk":     uc,
                                        "ref_chunk":      best_rc,
                                        "match_type":     mt,
                                        "similarity":     round(best_sim * 100, 1),
                                        "reference":      ref_name,
                                    }

                            for m in best_match_per_chunk.values():
                                matched.append(m)
                                type_counts[m["match_type"]] += 1
                            _diag_log.debug(f"  MATCHES: {type_counts}")

    # ── Table matching ───────────────────────────────────────────────────────
    def _table_to_text(t):
        try:
            import pandas as pd
            if isinstance(t, pd.DataFrame):
                return " ".join(str(v) for v in t.values.flatten()
                                if str(v) not in ("nan", "None", ""))
        except ImportError:
            pass
        if isinstance(t, (list, tuple)):
            return " ".join(
                str(cell)
                for row in t
                for cell in (row if isinstance(row, (list, tuple)) else [row])
                if str(cell) not in ("nan", "None", "")
            )
        return str(t)

    table_hits = 0
    for ut in user_tables:
        ut_text = _table_to_text(ut)
        if not ut_text.strip():
            continue
        for rt in ref_tables:
            rt_text = _table_to_text(rt)
            if not rt_text.strip():
                continue
            e1, e2 = _l2_normalize(get_embeddings([ut_text, rt_text]))
            sim    = float(np.dot(e1, e2))
            _diag_log.debug(f"  TABLE sim={sim:.4f}  threshold={TABLE_SIM_THRESHOLD}")
            if sim > TABLE_SIM_THRESHOLD:
                table_hits += 1
                break

    # ── Image matching ───────────────────────────────────────────────────────
    def _safe_image_similarity(img_a, img_b, target_size=(256, 256)):
        try:
            from PIL import Image as PILImage
            def _to_pil(img):
                if isinstance(img, PILImage.Image):
                    return img
                if isinstance(img, np.ndarray):
                    return PILImage.fromarray(img.astype("uint8"))
                if isinstance(img, (str, bytes)):
                    return PILImage.open(img)
                raise TypeError(f"Unsupported image type: {type(img)}")
            a = _to_pil(img_a).convert("RGB").resize(target_size, PILImage.LANCZOS)
            b = _to_pil(img_b).convert("RGB").resize(target_size, PILImage.LANCZOS)
            return float(np.mean(np.abs(np.array(a, dtype=float) - np.array(b, dtype=float))))
        except Exception:
            return image_similarity(img_a, img_b)

    image_hits = 0
    for ui_ in user_images:
        for ri in ref_images:
            try:
                diff = _safe_image_similarity(ui_, ri)
                _diag_log.debug(f"  IMAGE diff={diff:.2f}  threshold={IMAGE_DIFF_THRESHOLD}")
                if diff < IMAGE_DIFF_THRESHOLD:
                    image_hits += 1
                    break
            except Exception as exc:
                _diag_log.debug(f"  IMAGE comparison error: {exc}")

    _diag_log.debug(f"  table_hits={table_hits}  image_hits={image_hits}")

    type_counts["direct"] += table_hits + image_hits
    total_matched  = sum(type_counts.values())
    similarity     = round(min(total_matched / uncited_total * 100, 100.0), 1)

    _diag_log.debug(f"  uncited_total={uncited_total}  total_matched={total_matched}")
    _diag_log.debug(f"  FINAL similarity: {similarity}%")

    return {
        "reference":     ref_name,
        "similarity":    similarity,
        "match_types":   type_counts,
        "table_matches": table_hits,
        "image_matches": image_hits,
        "uncited_total": uncited_total,
    }, matched

# ---------------------------------------------------------------------------
# Public detection API
# ---------------------------------------------------------------------------

def check_plagiarism(user_pdf_path, reference_paths):
    global _degraded_mode

    # ── Check model availability and set degraded mode ───────────────────────
    # Try a test embedding to see if the model is available
    test_emb = get_embeddings(["test probe sentence"])
    _degraded_mode = (test_emb is None)

    if _degraded_mode:
        _diag_log.warning("=" * 60)
        _diag_log.warning("RUNNING IN DEGRADED MODE - BM25 KEYWORD MATCHING ONLY")
        _diag_log.warning("Semantic and paraphrase detection DISABLED")
        _diag_log.warning("Only direct word-overlap matches (>=75%) will be detected")
        _diag_log.warning("=" * 60)

    raw_text     = extract_text(user_pdf_path)
    clean_text   = remove_references(raw_text)
    user_chunks  = _split_chunks(clean_text)
    user_tables  = extract_tables(user_pdf_path)
    user_images  = extract_images(user_pdf_path)
    uncited_mask = [not _is_cited(c) for c in user_chunks]

    _diag_log.debug(f"\n{'#'*60}")
    _diag_log.debug(f"USER PDF: {os.path.basename(user_pdf_path)}")
    _diag_log.debug(f"  degraded mode  : {_degraded_mode}")
    _diag_log.debug(f"  total chunks   : {len(user_chunks)}")
    _diag_log.debug(f"  uncited chunks : {sum(uncited_mask)}")

    all_results, all_details = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_check_one_reference,
                        ref_path, user_chunks, uncited_mask,
                        user_tables, user_images): ref_path
            for ref_path in reference_paths
        }
        for future in as_completed(futures):
            result, matched = future.result()
            all_results.append(result)
            all_details.extend(matched)

    all_details.sort(key=lambda d: d["similarity"], reverse=True)
    return all_results, all_details, user_chunks, uncited_mask

# ---------------------------------------------------------------------------
# Colour helpers  (identical to v5)
# ---------------------------------------------------------------------------
_PALETTES = [
    (colors.HexColor("#1a6a8a"), colors.HexColor("#d4eaf5")),
    (colors.HexColor("#c0622b"), colors.HexColor("#fbe8da")),
    (colors.HexColor("#2e7d32"), colors.HexColor("#dcedc8")),
    (colors.HexColor("#8e1c3e"), colors.HexColor("#fce4ec")),
    (colors.HexColor("#1a237e"), colors.HexColor("#e8eaf6")),
    (colors.HexColor("#4a148c"), colors.HexColor("#f3e5f5")),
    (colors.HexColor("#bf360c"), colors.HexColor("#fbe9e7")),
    (colors.HexColor("#004d40"), colors.HexColor("#e0f2f1")),
]
_PALETTE_TINTS = [
    ("#b8d6e3","#cfe6f0","#e5f2f8"),
    ("#f0c8aa","#f7ddc9","#fceee4"),
    ("#b8ddb9","#ccead0","#e2f4e3"),
    ("#f0b3c8","#f7cad9","#fce3ec"),
    ("#bdc3e5","#d0d5ef","#e6e8f7"),
    ("#d8b4e2","#e5caed","#f2e4f7"),
    ("#f5bda8","#fad1c2","#fde8df"),
    ("#9fd3cf","#bbe3e0","#d8f0ef"),
]
_PALETTE_FG_HEX = [
    "#0f4f6a","#8c4010","#1a5c1e","#6b0e28",
    "#0f1860","#370b62","#8c2308","#003530",
]
_MT_BADGE_HEX = {
    "direct":    "#c0392b",
    "paraphrase":"#b7770d",
    "semantic":  "#1a6a8a",
}
_FITZ_TINTS = [
    ((0.35,0.62,0.78),(0.53,0.74,0.86),(0.72,0.86,0.93)),
    ((0.88,0.48,0.24),(0.92,0.66,0.47),(0.96,0.82,0.70)),
    ((0.32,0.65,0.35),(0.52,0.77,0.54),(0.72,0.88,0.73)),
    ((0.72,0.17,0.33),(0.84,0.48,0.59),(0.93,0.74,0.80)),
    ((0.18,0.23,0.72),(0.46,0.50,0.84),(0.72,0.74,0.93)),
    ((0.43,0.12,0.68),(0.64,0.46,0.82),(0.83,0.74,0.93)),
    ((0.82,0.26,0.08),(0.90,0.53,0.39),(0.96,0.77,0.69)),
    ((0.00,0.42,0.38),(0.28,0.64,0.60),(0.58,0.82,0.80)),
]
_FITZ_ALPHA = 0.38

def _pfg(i):  return _PALETTES[i % len(_PALETTES)][0]
def _pbg(i):  return _PALETTES[i % len(_PALETTES)][1]

def _bg_hex(palette_idx, match_type):
    tints = _PALETTE_TINTS[palette_idx % len(_PALETTE_TINTS)]
    if match_type == "direct":     return tints[0]
    if match_type == "paraphrase": return tints[1]
    return tints[2]

def _fg_hex(palette_idx):
    return _PALETTE_FG_HEX[palette_idx % len(_PALETTE_FG_HEX)]

def _score_color(v):
    if v >= 60: return colors.HexColor("#c0392b")
    if v >= 20: return colors.HexColor("#f39c12")
    return           colors.HexColor("#27ae60")

def _fitz_color(palette_idx: int, match_type: str):
    row = _FITZ_TINTS[palette_idx % len(_FITZ_TINTS)]
    if match_type == "direct":     return row[0]
    if match_type == "paraphrase": return row[1]
    return row[2]

# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------
_style_counter = [0]
def _new_ps(base, **kw):
    _style_counter[0] += 1
    return ParagraphStyle("s" + str(_style_counter[0]), parent=base, **kw)

def _esc(text):
    return text.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

_SENT_SPLIT = re.compile(r'(?<=[.!?…])\s+')
def _split_sentences(text):
    parts = _SENT_SPLIT.split(text.strip())
    return [p.strip() for p in parts if p.strip()]

# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------
def _calc_stats(r, uncited_total):
    tc = max(r.get("uncited_total", uncited_total), 1)
    mt = r["match_types"]
    d  = round(mt["direct"]     / tc * 100, 1)
    p  = round(mt["paraphrase"] / tc * 100, 1)
    se = round(mt["semantic"]   / tc * 100, 1)
    display_pct = round(min(d + p + se, 100.0), 1)
    _ROW_LABELS = {"direct":"Publication","paraphrase":"Student Paper","semantic":"Internet Source"}
    dominant    = max(mt, key=mt.get) if sum(mt.values()) else "semantic"
    type_label  = _ROW_LABELS[dominant]
    non_zero    = [k for k, v in mt.items() if v > 0]
    single_type = len(non_zero) == 1
    type_parts  = []
    if d  > 0: type_parts.append(f"Dir {d}%")
    if p  > 0: type_parts.append(f"Par {p}%")
    if se > 0: type_parts.append(f"Sem {se}%")
    return {
        "direct": d, "paraphrase": p, "semantic": se,
        "display_pct": display_pct,
        "single_type": single_type,
        "display_type_label": (_new_ps if False else
            {"Direct Match":"Direct Match","Paraphrasing":"Paraphrasing",
             "Semantic Similarity":"Semantic Similarity"}.get(
            {"direct":"Direct Match","paraphrase":"Paraphrasing","semantic":"Semantic Similarity"}.get(
            non_zero[0],"") if single_type else "", "")),
        "breakdown_label": "  ·  ".join(type_parts) or "No match",
        "non_zero_count":  len(non_zero),
        "counts":          mt,
        "type_label":      type_label,
    }

# ---------------------------------------------------------------------------
# Report builder  — identical to v5, drives from new chunk indices
# ---------------------------------------------------------------------------

def _build_report(user_pdf_path, results, details, user_chunks, uncited_mask, output_path):
    styles      = getSampleStyleSheet()
    NR          = styles["Normal"]
    PAGE_W, PAGE_H = A4
    ML = MR     = 1.5 * cm
    HDR_H       = 1.2 * cm
    SUM_ML = SUM_MR = 1.4 * cm
    SUM_W       = PAGE_W - SUM_ML - SUM_MR

    uncited_total = max(sum(uncited_mask), 1)
    matched_refs  = [r for r in results if sum(r["match_types"].values()) > 0]
    _ROW_LABELS   = {"direct":"Publication","paraphrase":"Student Paper","semantic":"Internet Source"}

    for r in matched_refs:
        tc  = max(r.get("uncited_total", uncited_total), 1)
        mt  = r["match_types"]
        d   = round(mt["direct"]     / tc * 100, 1)
        p   = round(mt["paraphrase"] / tc * 100, 1)
        se  = round(mt["semantic"]   / tc * 100, 1)
        display_pct = round(min(d + p + se, 100.0), 1)
        type_parts  = []
        if d  > 0: type_parts.append(f"Dir {d}%")
        if p  > 0: type_parts.append(f"Par {p}%")
        if se > 0: type_parts.append(f"Sem {se}%")
        r["_st"] = {"d":d,"p":p,"se":se,"display_pct":display_pct,
                    "breakdown_label": "  ·  ".join(type_parts) or "No match"}

    matched_refs.sort(key=lambda r: r["_st"]["display_pct"], reverse=True)
    src_idx = {r["reference"]: i for i, r in enumerate(matched_refs)}

    _MT_PRIORITY = {"direct":3,"paraphrase":2,"semantic":1}
    chunk_detail: dict = {}
    for d_item in details:
        ci   = d_item["user_chunk_idx"]
        prev = chunk_detail.get(ci)
        if prev is None:
            chunk_detail[ci] = d_item
        else:
            new_pri  = _MT_PRIORITY.get(d_item["match_type"], 0)
            prev_pri = _MT_PRIORITY.get(prev["match_type"], 0)
            if new_pri > prev_pri or (new_pri == prev_pri
                    and d_item["similarity"] > prev["similarity"]):
                chunk_detail[ci] = d_item

    ov_type_counts = {"direct":0,"paraphrase":0,"semantic":0}
    for cd in chunk_detail.values():
        ov_type_counts[cd["match_type"]] += 1
    max_media_direct = max((r["table_matches"]+r["image_matches"] for r in results), default=0)
    ov_type_counts["direct"] += max_media_direct

    ov_d  = round(ov_type_counts["direct"]     / uncited_total * 100, 1)
    ov_p  = round(ov_type_counts["paraphrase"] / uncited_total * 100, 1)
    ov_se = round(ov_type_counts["semantic"]   / uncited_total * 100, 1)
    ov_top = round(min(ov_d + ov_p + ov_se, 100.0), 1)

    # ── 2. Match Overview page ───────────────────────────────────────────────
    ov_buf  = io.BytesIO()
    BOT_OV  = 1.5 * cm
    FH_OV   = PAGE_H - HDR_H - BOT_OV
    ov_doc  = BaseDocTemplate(ov_buf, pagesize=A4)
    full_ov = Frame(ML, BOT_OV, PAGE_W - ML - MR, FH_OV, id="ov",
                    leftPadding=6, rightPadding=6, topPadding=8, bottomPadding=4)

    def _draw_ov_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#1a252f"))
        canvas.rect(0, PAGE_H - HDR_H, PAGE_W, HDR_H, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(ML, PAGE_H - 1.0*cm, os.path.basename(user_pdf_path))
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#aab7b8"))
        canvas.drawString(ML, PAGE_H - 1.6*cm, "Plagiarism Detection Report  ·  Match Overview  "
                          f"[Offline MiniLM-L6-v2  |  word-slide chunking]")
        canvas.drawRightString(PAGE_W - MR, PAGE_H - 1.0*cm,
                               f"Direct {ov_d}%  ·  Paraphrase {ov_p}%  ·  Semantic {ov_se}%")
        canvas.restoreState()

    ov_doc.addPageTemplates([PageTemplate(id="OV", frames=[full_ov], onPage=_draw_ov_page)])
    ov_story = [Spacer(1, 14)]

    OV_COL = 1.6 * cm
    ov_tbl = Table([[
        Paragraph(f"<b>{ov_top}%</b>",
                  _new_ps(NR, fontSize=28, textColor=_score_color(ov_top), leading=32)),
        Paragraph(f"<b>{ov_d}%</b><br/><font color='#7f8c8d' size='6'>Direct Match</font>",
                  _new_ps(NR, fontSize=11, textColor=colors.HexColor("#1a6a8a"), leading=14)),
        Paragraph(f"<b>{ov_p}%</b><br/><font color='#7f8c8d' size='6'>Paraphrasing</font>",
                  _new_ps(NR, fontSize=11, textColor=colors.HexColor("#c0622b"), leading=14)),
        Paragraph(f"<b>{ov_se}%</b><br/><font color='#7f8c8d' size='6'>Semantic</font>",
                  _new_ps(NR, fontSize=11, textColor=colors.HexColor("#2e7d32"), leading=14)),
    ]], colWidths=[OV_COL*2]*4)
    ov_tbl.setStyle(TableStyle([
        ("VALIGN",     (0,0),(-1,-1),"MIDDLE"),
        ("LINEAFTER",  (0,0),(2,0),  0.5, colors.HexColor("#bdc3c7")),
        ("LEFTPADDING",(0,0),(-1,-1), 12),
    ]))
    ov_story.append(ov_tbl)
    ov_story.append(Spacer(1, 18))
    ov_story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d5d8dc")))
    ov_story.append(Spacer(1, 12))
    ov_story.append(Paragraph("<b>Sources</b>",
                               _new_ps(NR, fontSize=9, fontName="Helvetica-Bold",
                                       textColor=colors.HexColor("#2c3e50"), spaceAfter=8, leading=12)))

    BADGE_W = 0.7 * cm
    ARR_W   = 0.5 * cm
    PCT_W   = 1.3 * cm
    NAME_W  = PAGE_W - ML - MR - BADGE_W - PCT_W - ARR_W - 0.3*cm

    for si, r in enumerate(matched_refs):
        st      = r["_st"]
        src_row = Table([[
            Paragraph(str(si+1), _new_ps(NR, fontSize=8, textColor=colors.white,
                                          alignment=TA_CENTER, leading=10)),
            [Paragraph(f"<b>{r['reference']}</b>",
                       _new_ps(NR, fontSize=8, textColor=colors.HexColor("#1a252f"), leading=10)),
             Paragraph(st["breakdown_label"],
                       _new_ps(NR, fontSize=6, textColor=colors.HexColor("#aab7b8"), leading=8))],
            Paragraph(f"<b>{st['display_pct']}%</b>",
                      _new_ps(NR, fontSize=10, textColor=colors.HexColor("#2c3e50"),
                               alignment=TA_RIGHT, leading=12)),
            Paragraph("<b>&gt;</b>",
                      _new_ps(NR, fontSize=10, textColor=colors.HexColor("#bdc3c7"),
                               alignment=TA_CENTER, leading=12)),
        ]], colWidths=[BADGE_W, NAME_W, PCT_W, ARR_W])
        src_row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0),  _pfg(si)),
            ("BACKGROUND",    (1,0),(-1,0), colors.white),
            ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ("LEFTPADDING",   (0,0),(0,0),  0),
            ("LEFTPADDING",   (1,0),(1,0),  10),
            ("LEFTPADDING",   (2,0),(-1,-1), 4),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("LINEBELOW",     (0,0),(-1,-1), 0.5, colors.HexColor("#ecf0f1")),
        ]))
        ov_story.append(src_row)

    ov_doc.build(ov_story)
    ov_buf.seek(0)

    # ── 3. Summary page ──────────────────────────────────────────────────────
    sum_buf = io.BytesIO()
    BOT_SUM = 1.5 * cm
    FH_SUM  = PAGE_H - HDR_H - BOT_SUM
    sum_doc = BaseDocTemplate(sum_buf, pagesize=A4)
    sum_frm = Frame(SUM_ML, BOT_SUM, SUM_W, FH_SUM, id="S",
                    leftPadding=6, rightPadding=6, topPadding=10, bottomPadding=4)

    def _draw_sum_page(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#1a252f"))
        canvas.rect(0, PAGE_H - HDR_H, PAGE_W, HDR_H, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.drawString(ML, PAGE_H - 1.0*cm, os.path.basename(user_pdf_path))
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#aab7b8"))
        canvas.drawString(ML, PAGE_H - 1.6*cm, "Plagiarism Detection Report  ·  Summary")
        canvas.restoreState()

    sum_doc.addPageTemplates([PageTemplate(id="SUM", frames=[sum_frm], onPage=_draw_sum_page)])

    sum_story = []
    sum_story.append(Paragraph("<b>Summary Analysis</b>",
                                _new_ps(NR, fontSize=14, fontName="Helvetica-Bold",
                                        textColor=colors.HexColor("#1a252f"),
                                        spaceAfter=4, leading=18)))
    sum_story.append(Paragraph(
        f"Document: <b>{os.path.basename(user_pdf_path)}</b> &nbsp;·&nbsp; "
        f"Uncited chunks: <b>{uncited_total}</b> &nbsp;·&nbsp; "
        f"Overall similarity: <b>{ov_top}%</b> &nbsp;·&nbsp; "
        f"Model: <b>all-MiniLM-L6-v2 (offline)</b>",
        _new_ps(NR, fontSize=8, textColor=colors.HexColor("#7f8c8d"),
                 spaceAfter=10, leading=11)))
    sum_story.append(HRFlowable(width=SUM_W, thickness=1.0, color=colors.HexColor("#c0392b")))
    sum_story.append(Spacer(1, 10))

    OV_COL2 = 1.6 * cm
    sum_story.append(Paragraph("<b>Overall Match Breakdown</b>",
                                _new_ps(NR, fontSize=9, fontName="Helvetica-Bold",
                                        textColor=colors.HexColor("#2c3e50"),
                                        spaceAfter=6, leading=12)))
    ovt = Table([[
        Paragraph(f"<b>{ov_top}%</b>",
                  _new_ps(NR, fontSize=18, textColor=colors.HexColor("#2c3e50"))),
        Paragraph(f"<b>{ov_d}%</b><br/><font color='#7f8c8d' size='6'>Direct Match</font>",
                  _new_ps(NR, fontSize=9, textColor=colors.HexColor("#1a6a8a"), leading=11)),
        Paragraph(f"<b>{ov_p}%</b><br/><font color='#7f8c8d' size='6'>Paraphrasing</font>",
                  _new_ps(NR, fontSize=9, textColor=colors.HexColor("#c0622b"), leading=11)),
        Paragraph(f"<b>{ov_se}%</b><br/><font color='#7f8c8d' size='6'>Semantic Similarity</font>",
                  _new_ps(NR, fontSize=9, textColor=colors.HexColor("#2e7d32"), leading=11)),
    ]], colWidths=[OV_COL2*1.5]*4)
    ovt.setStyle(TableStyle([
        ("VALIGN",     (0,0),(-1,-1),"MIDDLE"),
        ("LINEAFTER",  (0,0),(2,0),  0.5, colors.HexColor("#bdc3c7")),
        ("LEFTPADDING",(0,0),(-1,-1), 10),
    ]))
    sum_story.append(ovt)
    sum_story.append(Spacer(1, 15))

    sum_story.append(Paragraph("<b>Per-Reference PDF Breakdown</b>",
                                _new_ps(NR, fontSize=9, fontName="Helvetica-Bold",
                                        textColor=colors.HexColor("#2c3e50"),
                                        spaceAfter=6, leading=12)))

    _C0,_C1,_C2,_C3,_C4,_C5 = 0.5*cm, 6.0*cm, 2.0*cm, 2.0*cm, 2.0*cm, 2.0*cm

    def _hdr_p(txt, col):
        return Paragraph(f"<b>{txt}</b>",
                         _new_ps(NR, fontSize=7, textColor=col, alignment=TA_CENTER, leading=9))
    def _val_p(val, col):
        txt = f"{val}%" if val > 0 else "—"
        c   = col if val > 0 else colors.HexColor("#bdc3c7")
        return Paragraph(txt, _new_ps(NR, fontSize=8, textColor=c, alignment=TA_CENTER, leading=10))

    shdr = Table([[
        Paragraph("", _new_ps(NR, fontSize=1)),
        Paragraph("<b>Reference PDF</b>",
                  _new_ps(NR, fontSize=7, fontName="Helvetica-Bold",
                           textColor=colors.HexColor("#2c3e50"), leading=9)),
        _hdr_p("Total %",    colors.HexColor("#2c3e50")),
        _hdr_p("Direct",     colors.HexColor("#1a6a8a")),
        _hdr_p("Paraphrase", colors.HexColor("#c0622b")),
        _hdr_p("Semantic",   colors.HexColor("#2e7d32")),
    ]], colWidths=[_C0,_C1,_C2,_C3,_C4,_C5])
    shdr.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.HexColor("#ecf0f1")),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
    ]))
    sum_story.append(shdr)

    for si, r in enumerate(matched_refs):
        st  = r["_st"]
        row = Table([[
            Paragraph("", _new_ps(NR, fontSize=1)),
            Paragraph(r["reference"],
                      _new_ps(NR, fontSize=7, textColor=colors.HexColor("#2c3e50"), leading=9)),
            _val_p(st["display_pct"], colors.HexColor("#2c3e50")),
            _val_p(st["d"],           colors.HexColor("#1a6a8a")),
            _val_p(st["p"],           colors.HexColor("#c0622b")),
            _val_p(st["se"],          colors.HexColor("#2e7d32")),
        ]], colWidths=[_C0,_C1,_C2,_C3,_C4,_C5])
        row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(0,0),  _pfg(si)),
            ("LINEBELOW",     (0,0),(-1,-1), 0.5, colors.HexColor("#ecf0f1")),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
        ]))
        sum_story.append(row)

    sum_doc.build(sum_story)
    sum_buf.seek(0)

    # ── 4. Annotate original PDF  (per-word conflict-resolution highlight) ─────
    #
    # Problem with the old approach: chunks overlap heavily (step=5, window=30).
    # The first chunk to claim a word "locked" it via word_assigned, so later
    # chunks from a *different* source could never recolor those words.  This
    # caused color from source-1 to bleed into source-2 territory.
    #
    # New approach — three passes:
    #   Pass 1: For every word position, collect ALL chunks that cover it and
    #           record (match_type_priority, similarity, source_idx, rgb).
    #   Pass 2: Each word is awarded to the SINGLE best claim
    #           (highest priority → highest similarity → lowest source_idx).
    #           If the word has NO claim at all it stays uncolored.
    #   Pass 3: Require a minimum consecutive run of words from the same source
    #           before actually drawing color.  Isolated 1-2 word "orphans" that
    #           appear between two different-source runs are NOT colored — this
    #           is the main anti-bleed gate.
    #   Pass 4: Merge adjacent same-color word rects on the same line and draw.

    _MIN_RUN = 3   # a source must own ≥ this many consecutive words to be colored

    src_doc = fitz.open(user_pdf_path)
    ann_doc = fitz.open(user_pdf_path)

    # Collect all words across pages in document order
    all_page_words: list[tuple[int, fitz.Rect, str]] = []
    for pno in range(len(src_doc)):
        page = src_doc[pno]
        for w in page.get_text("words"):
            all_page_words.append((pno, fitz.Rect(w[0], w[1], w[2], w[3]), w[4]))

    total_words = len(all_page_words)

    # ── Pass 1: map each word-index → best claim ────────────────────────────
    # word_best[word_idx] = (priority, similarity, source_idx, rgb) | None
    _MT_PRI = {"direct": 3, "paraphrase": 2, "semantic": 1}
    word_best: dict[int, tuple] = {}   # word_idx → (pri, sim, si, rgb)

    # build word-key → word_idx lookup so we can do O(1) lookups
    word_key_to_idx: dict[tuple, int] = {}
    for wi, pw in enumerate(all_page_words):
        key = (pw[0], round(pw[1].x0, 1), round(pw[1].y0, 1))
        word_key_to_idx[key] = wi

    ci = 0
    for i in range(0, max(total_words - MIN_CHUNK_WORDS + 1, 1), CHUNK_STEP):
        chunk_slice = all_page_words[i: i + CHUNK_WORDS]
        if len(chunk_slice) >= MIN_CHUNK_WORDS:
            if ci in chunk_detail:
                cd  = chunk_detail[ci]
                si  = src_idx.get(cd["reference"], 0)
                pri = _MT_PRI.get(cd["match_type"], 0)
                sim = cd.get("similarity", 0.0)
                rgb = _fitz_color(si, cd["match_type"])
                claim = (pri, sim, si, rgb)
                for pw in chunk_slice:
                    key = (pw[0], round(pw[1].x0, 1), round(pw[1].y0, 1))
                    wi  = word_key_to_idx.get(key)
                    if wi is None:
                        continue
                    prev = word_best.get(wi)
                    if prev is None:
                        word_best[wi] = claim
                    else:
                        # keep whichever claim is stronger
                        if (claim[0], claim[1], -claim[2]) > (prev[0], prev[1], -prev[2]):
                            word_best[wi] = claim
            ci += 1

    # ── Pass 2: build per-word color list (None = uncolored) ────────────────
    word_color: list[tuple | None] = [None] * total_words
    for wi, claim in word_best.items():
        word_color[wi] = claim[3]   # just the rgb tuple

    # ── Pass 3: suppress isolated runs shorter than _MIN_RUN ────────────────
    # Walk word_color; find contiguous runs of the same non-None color.
    # Any run shorter than _MIN_RUN is reset to None.
    idx = 0
    while idx < total_words:
        if word_color[idx] is None:
            idx += 1
            continue
        run_color = word_color[idx]
        run_start = idx
        while idx < total_words and word_color[idx] == run_color:
            idx += 1
        run_len = idx - run_start
        if run_len < _MIN_RUN:
            for j in range(run_start, idx):
                word_color[j] = None

    # ── Pass 4: collect rects per page+color, merge, draw ───────────────────
    page_annots: dict[int, list[tuple[fitz.Rect, tuple]]] = defaultdict(list)
    for wi, rgb in enumerate(word_color):
        if rgb is None:
            continue
        pno, rect, _ = all_page_words[wi]
        page_annots[pno].append((rect, rgb))

    for pno, annot_list in page_annots.items():
        pg = ann_doc[pno]
        color_rects: dict[tuple, list[fitz.Rect]] = defaultdict(list)
        for rect, rgb in annot_list:
            color_rects[rgb].append(rect)
        for rgb, rects in color_rects.items():
            rects_sorted = sorted(rects, key=lambda r: (round(r.y0, 1), r.x0))
            merged: list[fitz.Rect] = []
            for r in rects_sorted:
                if merged and abs(r.y0 - merged[-1].y0) < 3 and r.x0 <= merged[-1].x1 + 6:
                    merged[-1] = fitz.Rect(merged[-1].x0, min(merged[-1].y0, r.y0),
                                           max(merged[-1].x1, r.x1), max(merged[-1].y1, r.y1))
                else:
                    merged.append(fitz.Rect(r))
            for rect in merged:
                ann = pg.add_highlight_annot(rect)
                ann.set_colors(stroke=rgb)
                ann.set_opacity(_FITZ_ALPHA)
                ann.update()

    ann_buf = io.BytesIO()
    ann_doc.save(ann_buf, garbage=4, deflate=True)
    ann_doc.close(); src_doc.close()
    ann_buf.seek(0)

    # ── 5. Merge Overview + Annotated PDF + Summary ───────────────────────────
    final_doc = fitz.open()
    ov_fitz   = fitz.open("pdf", ov_buf.read())
    ann_fitz  = fitz.open("pdf", ann_buf.read())
    sum_fitz  = fitz.open("pdf", sum_buf.read())
    final_doc.insert_pdf(ov_fitz)
    final_doc.insert_pdf(ann_fitz)
    final_doc.insert_pdf(sum_fitz)
    final_doc.save(output_path, garbage=4, deflate=True)
    final_doc.close()
    ov_fitz.close(); ann_fitz.close(); sum_fitz.close()

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run_engine(username, role, uploaded_pdf_path):
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    reference_pdfs = [
        os.path.join(REFERENCE_DIR, f)
        for f in sorted(os.listdir(REFERENCE_DIR))
        if f.lower().endswith(".pdf")
    ]
    if not reference_pdfs:
        raise ValueError(
            "No reference PDFs found. Ask your admin to upload reference documents first."
        )
    out_dir     = os.path.join(RESULT_ROOT, username)
    os.makedirs(out_dir, exist_ok=True)
    base        = os.path.splitext(os.path.basename(uploaded_pdf_path))[0]
    output_path = os.path.join(out_dir, base + "_report_offline.pdf")

    results, details, user_chunks, uncited_mask = check_plagiarism(
        uploaded_pdf_path, reference_pdfs)

    _build_report(
        user_pdf_path = uploaded_pdf_path,
        results       = results,
        details       = details,
        user_chunks   = user_chunks,
        uncited_mask  = uncited_mask,
        output_path   = output_path,
    )
    save_result(username, role, uploaded_pdf_path, output_path, results)
    return output_path, results, details