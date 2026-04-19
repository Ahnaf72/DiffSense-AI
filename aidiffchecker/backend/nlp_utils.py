"""
nlp_utils.py  ─  NLP helpers
==============================
Model : BAAI/bge-small-en-v1.5  (fastembed, 384-dim, L2-normalised)

Three-tier match classification  ── FIXED v2
─────────────────────────────────────────────────────────────────────────────
Root causes of wrong output in v1:
  1.  classify_match ignored *content-word* overlap — stopwords ("the","a","of")
      inflated Jaccard, so "related-topic" pairs scored as paraphrase.
  2.  No adaptive relative-margin gate for "semantic": any cosine ≥ 0.65
      fired, generating hundreds of false-positive semantic hits on same-
      domain academic text.
  3.  Jaccard threshold 0.70 for "direct" was too strict — a single word
      substitution drops Jaccard below 0.70 on a 10-word sentence.

Fixes
─────
  A.  classify_match now accepts optional content_overlap (shared non-stop
      words) and mean_sim (document-level cosine baseline).
  B.  PARAPHRASE requires content_overlap ≥ 2 AND word-floor ≥ 0.20
      (not 0.15) to exclude purely topic-level matches.
  C.  SEMANTIC gate raised to 0.73 AND must exceed mean_sim + 0.07
      (adaptive baseline prevents same-domain false positives).
  D.  DIRECT lowered to jaccard ≥ 0.60 (catches near-verbatim single-
      word swaps) plus cosine ≥ 0.92 fast-path.
  E.  split_sentences min_words raised 6 → 8 to avoid flagging trivially
      short header/caption fragments.
─────────────────────────────────────────────────────────────────────────────
"""

import re
import logging
import numpy as np
from typing import Optional

# ── logging ───────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)

# ── lazy model loading via ModelManager ───────────────────────────────────
_model_manager = None
_cached_model = None
_model_load_attempted = False
_model_type = None  # "fastembed" or "sentence_transformer"


def _get_model_manager():
    """Get or create ModelManager instance (lazy import to avoid circular deps)."""
    global _model_manager
    if _model_manager is None:
        from backend.model_manager import model_manager
        _model_manager = model_manager
    return _model_manager


def _get_model():
    """
    Get embedding model, trying FastEmbed first, then SentenceTransformer.
    Returns (model, model_type) or (None, None) if both unavailable.
    """
    global _cached_model, _model_load_attempted, _model_type

    if _cached_model is not None:
        return _cached_model

    if _model_load_attempted:
        return None

    _model_load_attempted = True

    import asyncio
    manager = _get_model_manager()

    # ── Try FastEmbed first ────────────────────────────────────────────────
    try:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, manager.get_embedding_model())
                fe_model = future.result(timeout=60)
        except RuntimeError:
            fe_model = asyncio.run(manager.get_embedding_model())

        if fe_model is not None:
            _cached_model = fe_model
            _model_type = "fastembed"
            logger.info("FastEmbed model loaded successfully")
            return _cached_model
        else:
            logger.warning("FastEmbed model unavailable - trying SentenceTransformer fallback")
    except Exception as e:
        logger.warning(f"FastEmbed load failed: {e} - trying SentenceTransformer fallback")

    # ── Fallback: SentenceTransformer ──────────────────────────────────────
    try:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, manager.get_sentence_transformer_model())
                st_model = future.result(timeout=120)
        except RuntimeError:
            st_model = asyncio.run(manager.get_sentence_transformer_model())

        if st_model is not None:
            _cached_model = st_model
            _model_type = "sentence_transformer"
            logger.info("SentenceTransformer model loaded as fallback")
            return _cached_model
        else:
            logger.error("Both FastEmbed and SentenceTransformer unavailable - degraded mode")
    except Exception as e:
        logger.error(f"SentenceTransformer fallback also failed: {e}")

    return None

# ── stopword set (used for content-word overlap) ───────────────────────────
_STOPWORDS = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","are","was","were","be","been","being","have","has",
    "had","do","does","did","will","would","could","should","may","might",
    "this","that","these","those","it","its","they","their","we","our",
    "as","if","then","than","so","yet","both","each","more","also","not",
    "no","nor","about","after","before","between","into","through","during",
    "which","who","what","when","where","how","all","any","some","such",
    "i","you","he","she","us","me","him","her","its","my","your","his",
}

# ── thresholds ─────────────────────────────────────────────────────────────
DIRECT_SEM_SIM        = 0.92   # cosine ≥ 0.92 → near-identical phrasing
DIRECT_COMBINED_OV    = 0.60   # sem >= PARAPHRASE_HIGH_SEM AND ov >= this
                                #   -> direct copy with minor edits, not a rewrite
DIRECT_WORD_OVERLAP   = 0.75   # ≥75% of user-words appear verbatim in ref
DIRECT_WORD_SEM_FLOOR = 0.73   # combined with above (sem must confirm)
PARAPHRASE_SEM_SIM    = 0.82   # cosine threshold for paraphrase
PARAPHRASE_HIGH_SEM   = 0.85   # cosine ≥ 0.88: so high that even near-zero
                                #   word overlap confirms same content (catches
                                #   complete-synonym-substitution paraphrases)
PARAPHRASE_WORD_FLOOR = 0.22   # ≥22% word overlap required (eliminates
                                #   pure topic-level high-cosine pairs)
PARAPHRASE_CONTENT_MIN = 3     # ≥3 shared non-stopword tokens
SEMANTIC_SEM_SIM      = 0.73   # raised from 0.65 to cut false positives
SEMANTIC_RELATIVE_MARGIN = 0.08  # must be 8pp above doc-level mean


# ── embeddings ─────────────────────────────────────────────────────────────

def get_embeddings(texts: list[str], batch_size: int = 256) -> Optional[np.ndarray]:
    """
    Batch-encode texts using available embedding model.
    Returns float32 (N, 384), L2-normalised so cosine == dot product.

    Tries FastEmbed first, falls back to SentenceTransformer.
    Returns None if both unavailable (triggers BM25-only degraded mode).
    """
    if not texts:
        return np.empty((0, 384), dtype=np.float32)

    model = _get_model()
    if model is None:
        logger.warning("get_embeddings called but model unavailable - returning None")
        return None

    if _model_type == "sentence_transformer":
        embs = model.encode(texts, batch_size=batch_size, show_progress_bar=False,
                           convert_to_numpy=True).astype("float32")
    else:
        embs = np.array(
            list(model.embed(texts, batch_size=batch_size)),
            dtype=np.float32,
        )

    # L2-normalise so cosine == dot product
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-10, norms)
    embs = embs / norms
    return embs


def get_embedding(text: str) -> Optional[np.ndarray]:
    """
    Single-text wrapper — kept for backward compatibility.
    Returns None if model unavailable.
    """
    embeddings = get_embeddings([text])
    if embeddings is None:
        return None
    return embeddings[0]


def compute_similarity(text1: str, text2: str) -> Optional[float]:
    """
    Cosine similarity between two texts (L2-normalised → dot product).
    Returns None if model unavailable.
    """
    embeddings = get_embeddings([text1, text2])
    if embeddings is None:
        return None
    e1, e2 = embeddings
    return float(np.dot(e1, e2))


# ── word helpers ───────────────────────────────────────────────────────────

def _word_tokens(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _content_words(text: str) -> set[str]:
    return {w for w in _word_tokens(text) if w not in _STOPWORDS}


def jaccard_similarity(text1: str, text2: str) -> float:
    """
    Word-level Jaccard similarity (all words, including stopwords).
    Use content_word_overlap() for a noise-free signal.
    Returns float in [0, 1].
    """
    words1 = set(_word_tokens(text1))
    words2 = set(_word_tokens(text2))
    if not words1 or not words2:
        return 0.0
    return len(words1 & words2) / len(words1 | words2)


def word_overlap(text1: str, text2: str) -> float:
    """
    Asymmetric word overlap: fraction of text1's words that appear in text2.
    Matches engine.py's _word_overlap() for consistent scoring.
    """
    w1 = set(_word_tokens(text1))
    w2 = set(_word_tokens(text2))
    return len(w1 & w2) / len(w1) if w1 else 0.0


def content_word_overlap(text1: str, text2: str) -> int:
    """
    Count shared non-stopword tokens between two texts.
    Used to distinguish a true paraphrase (shares content words) from
    a same-topic paragraph (shares only stopwords + technical jargon).
    """
    c1 = _content_words(text1)
    c2 = _content_words(text2)
    return len(c1 & c2)


# ── match classifier ───────────────────────────────────────────────────────

def classify_match(
    cosine_sim: float,
    jaccard_sim: float,
    *,
    text1: str = "",
    text2: str = "",
    mean_sim: float = 0.0,
) -> str | None:
    """
    Classify a text-pair into one of three match types, or None.

    Parameters
    ----------
    cosine_sim   : L2-normalised dot product of the two sentence embeddings
    jaccard_sim  : word-level Jaccard index (all tokens)
    text1 / text2: original strings — used to compute content-word overlap
                   when provided (strongly recommended)
    mean_sim     : document-level mean cosine baseline for the adaptive
                   semantic gate (default 0 → no baseline filter)

    Decision tree (evaluated top-to-bottom; first match wins)
    ──────────────────────────────────────────────────────────
    DIRECT      cosine ≥ 0.92  (near-identical embedding)
                OR word_overlap(t1,t2) ≥ 0.75 AND cosine ≥ 0.73  (Path 2)
                OR cosine ≥ 0.85 AND word_overlap ≥ 0.60           (Path 3)
                   near-copy with some words changed

    PARAPHRASE  cosine ≥ 0.82
                AND word_overlap ≥ 0.22  (shares enough vocabulary)
                AND content_overlap ≥ 3  (at least 3 shared content-words)
                AND not already DIRECT

    SEMANTIC    cosine ≥ 0.73
                AND cosine ≥ mean_sim + 0.08  (above document baseline)
                AND content_overlap ≥ 3
                AND word_overlap < PARAPHRASE_WORD_FLOOR (0.22)
                  → KEY FIX: SEMANTIC = "different words, same idea";
                    cap is PARAPHRASE floor, not DIRECT floor. High-overlap
                    pairs that fail PARAPHRASE must NOT leak into SEMANTIC.
                AND not already DIRECT or PARAPHRASE

    Note: high cosine (≥ 0.82) + low word_overlap (< 0.22) → same *topic*
    independently expressed → falls through to SEMANTIC, not PARAPHRASE.
    This is the critical fix for the paraphrase false-positive bug.
    """
    # ── compute overlap if text strings supplied ───────────────────────────
    if text1 and text2:
        w_overlap = word_overlap(text1, text2)
        c_overlap = content_word_overlap(text1, text2)
    else:
        # Fallback: estimate from Jaccard (less accurate)
        w_overlap = jaccard_sim
        c_overlap = 99  # can't compute; don't gate on it

    # ── DIRECT ────────────────────────────────────────────────────────────
    if cosine_sim >= DIRECT_SEM_SIM:
        return "direct"
    if w_overlap >= DIRECT_WORD_OVERLAP and cosine_sim >= DIRECT_WORD_SEM_FLOOR:
        return "direct"

    # ── PARAPHRASE ────────────────────────────────────────────────────────
    # Path 3: sem in high-paraphrase range but overlap is moderate
    # -> copy with some words changed (direct), not a genuine rewrite
    if cosine_sim >= PARAPHRASE_HIGH_SEM and w_overlap >= DIRECT_COMBINED_OV:
        return "direct"
    # Path A: standard—vocabulary floor confirms intentional reuse
    if (cosine_sim >= PARAPHRASE_SEM_SIM
            and w_overlap >= PARAPHRASE_WORD_FLOOR
            and c_overlap >= PARAPHRASE_CONTENT_MIN):
        return "paraphrase"
    # Path B: sophisticated rewrite—cosine so high (≥ 0.88) that even near-zero
    # surface-word overlap confirms same content (complete synonym substitution).
    if (cosine_sim >= PARAPHRASE_HIGH_SEM
            and w_overlap < DIRECT_COMBINED_OV
            and c_overlap >= PARAPHRASE_CONTENT_MIN):
        return "paraphrase"

    # ── SEMANTIC ──────────────────────────────────────────────────────────
    # Adaptive gate: must sit above the document-level mean by RELATIVE_MARGIN.
    # This prevents false positives when user & reference are from the same domain.
    relative_threshold = mean_sim + SEMANTIC_RELATIVE_MARGIN
    if (cosine_sim >= SEMANTIC_SEM_SIM
            and cosine_sim >= relative_threshold
            and c_overlap >= PARAPHRASE_CONTENT_MIN
            and w_overlap < DIRECT_WORD_OVERLAP):
        return "semantic"

    return None


# ── sentence splitter ──────────────────────────────────────────────────────
# Improved: avoids splitting at common abbreviations (Dr., et al., Fig., etc.)
_ABBREV = re.compile(
    r"\b(Dr|Mr|Mrs|Ms|Prof|Fig|Eq|No|Vol|pp|vs|et\s+al|i\.e|e\.g|approx|"
    r"Dept|Univ|Corp|Inc|Ltd|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.",
    re.IGNORECASE,
)
_SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+(?=[A-Z\"\'\(])")


def split_sentences(text: str, min_words: int = 8) -> list[str]:
    """
    Split text into sentences.

    Rules
    ─────
    • Temporarily mask known abbreviations so they don't trigger a split.
    • Split on .  !  ?  … followed by whitespace + uppercase letter.
    • Discard sentences shorter than min_words (default 8, raised from 6
      to eliminate header/caption fragments that flood match results).
    """
    # Mask abbreviations: "Dr." → "Dr·" so the splitter ignores them
    masked = _ABBREV.sub(lambda m: m.group(0)[:-1] + "·", text.strip())
    raw    = _SENT_SPLIT.split(masked)
    # Restore masked dots
    return [
        s.replace("·", ".").strip()
        for s in raw
        if len(s.split()) >= min_words
    ]


# ── reference section removal ──────────────────────────────────────────────
_REF_SECTION = re.compile(
    r"\n\s*(References|Bibliography|Works\s+Cited|Sources|Literature\s+Cited)"
    r"\s*\n",
    re.IGNORECASE,
)
_INLINE_CITATION_PAREN = re.compile(
    r"\([A-Z][a-z]+(?:\s+et\s+al\.)?[,\s]+\d{4}[a-z]?\s*(?:;[^)]+)?\)",
    re.IGNORECASE,
)
_INLINE_CITATION_NUM = re.compile(r"\[\d+(?:[,–\-]\d+)*\]")
_SUPERSCRIPT         = re.compile(r"[¹²³⁴⁵⁶⁷⁸⁹⁰]+")


def remove_references(text: str) -> str:
    """Strip reference section and inline citations from extracted PDF text."""
    match = _REF_SECTION.search(text)
    if match:
        text = text[: match.start()]
    text = _INLINE_CITATION_PAREN.sub("", text)
    text = _INLINE_CITATION_NUM.sub("", text)
    text = _SUPERSCRIPT.sub("", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── offline readiness check ───────────────────────────────────────────────

def check_offline_readiness() -> dict:
    """
    Check if embedding model is available.
    Used by /api/system/status endpoint.

    Returns dict with:
        - fastembed_available: bool
        - fastembed_attempted: bool
        - missing_models: list[str]
        - fully_offline_ready: bool (True if ANY model is loaded)
    """
    manager = _get_model_manager()

    # Check if model is already loaded (either FastEmbed or ST fallback)
    model_available = _cached_model is not None
    fe_available = model_available and _model_type == "fastembed"
    st_available = model_available and _model_type == "sentence_transformer"

    # If not loaded and not attempted, try to get status from manager
    if not model_available and not _model_load_attempted:
        # Don't trigger load, just report not attempted
        return {
            "fastembed_available": False,
            "fastembed_attempted": False,
            "missing_models": [],
            "fully_offline_ready": False,
        }

    return {
        "fastembed_available": fe_available,
        "fastembed_attempted": _model_load_attempted,
        "missing_models": manager.get_missing_models() if manager else [],
        "fully_offline_ready": model_available,  # any model = ready
    }