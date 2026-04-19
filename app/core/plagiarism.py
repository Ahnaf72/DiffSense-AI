"""Direct plagiarism detection via n-gram hash matching.

Compares document chunks against a reference corpus using overlapping
n-gram (shingle) fingerprints.  This catches **exact and near-exact**
copying that semantic embedding similarity may miss or dilute.

Algorithm:
  1. Tokenise text into words (lowercased, punctuation stripped).
  2. Slide a window of *n* words to produce n-grams.
  3. Hash each n-gram (xxhash for speed, falls back to built-in hash).
  4. Build a fingerprint set per chunk.
  5. Jaccard similarity = |intersection| / |union| of two fingerprint sets.

Usage:
    from app.core.plagiarism import extract_ngrams, ngram_fingerprint, jaccard_similarity
    from app.core.plagiarism import detect_plagiarism

    matches = detect_plagiarism(doc_chunks, ref_chunks, n=7)
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Tokenisation ──────────────────────────────────────────────────────

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenise(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into word tokens."""
    return _WORD_RE.findall(text.lower())


# ── N-gram extraction ────────────────────────────────────────────────


def extract_ngrams(text: str, *, n: int = 7) -> list[str]:
    """Extract overlapping word-level n-grams from *text*.

    Args:
        text: Input string.
        n: Number of words per n-gram (5–10 recommended).

    Returns:
        List of n-gram strings, e.g. ["the quick brown fox jumps", ...]
    """
    words = _tokenise(text)
    if len(words) < n:
        return []
    return [" ".join(words[i : i + n]) for i in range(len(words) - n + 1)]


# ── Fingerprinting (hashing) ──────────────────────────────────────────


def _hash_ngram(ngram: str) -> int:
    """Deterministic 64-bit hash of an n-gram string.

    Uses hashlib.sha256 (universally available) and takes the first 8 bytes
    as a signed 64-bit integer.  Deterministic across processes (unlike
    built-in ``hash()`` which is randomised in Python 3.3+).
    """
    digest = hashlib.sha256(ngram.encode("utf-8")).digest()[:8]
    return int.from_bytes(digest, "little", signed=True)


def ngram_fingerprint(text: str, *, n: int = 7) -> set[int]:
    """Return the set of hashed n-grams for *text*.

    This is the core data structure for fast set-based comparison.
    """
    ngrams = extract_ngrams(text, n=n)
    return {_hash_ngram(ng) for ng in ngrams}


# ── Similarity ────────────────────────────────────────────────────────


def jaccard_similarity(fp_a: set[int], fp_b: set[int]) -> float:
    """Jaccard index of two n-gram fingerprint sets.

    Returns a value in [0, 1] where 1 = identical n-gram sets.
    """
    if not fp_a or not fp_b:
        return 0.0
    intersection = len(fp_a & fp_b)
    union = len(fp_a | fp_b)
    return intersection / union if union else 0.0


def containment_score(fp_subset: set[int], fp_superset: set[int]) -> float:
    """Fraction of *fp_subset*'s n-grams that appear in *fp_superset*.

    This is more useful for plagiarism detection than Jaccard: a short
    copied passage inside a long document will have high containment but
    low Jaccard (because the union is dominated by the longer text).
    """
    if not fp_subset or not fp_superset:
        return 0.0
    return len(fp_subset & fp_superset) / len(fp_subset)


# ── Match dataclass ───────────────────────────────────────────────────


@dataclass
class PlagiarismMatch:
    """A single plagiarism match between a document chunk and a reference chunk."""

    upload_chunk_id: str
    upload_chunk_index: int
    upload_content: str
    reference_chunk_id: str
    reference_chunk_index: int
    reference_content: str
    jaccard_score: float
    containment_score: float
    matched_ngrams: list[str] = field(default_factory=list)


# ── Detection ─────────────────────────────────────────────────────────


def detect_plagiarism(
    doc_chunks: list[dict],
    ref_chunks: list[dict],
    *,
    n: int = 7,
    min_jaccard: float = 0.1,
    min_containment: float = 0.2,
    max_matches_per_chunk: int = 5,
) -> list[PlagiarismMatch]:
    """Detect direct plagiarism between document and reference chunks.

    For each document chunk, computes n-gram fingerprint similarity
    against every reference chunk and returns matches above threshold.

    Args:
        doc_chunks: List of dicts with keys: id, chunk_index, content.
        ref_chunks: List of dicts with keys: id, chunk_index, content.
        n: N-gram size (5–10 words recommended).
        min_jaccard: Minimum Jaccard similarity to report.
        min_containment: Minimum containment score to report.
        max_matches_per_chunk: Cap matches per doc chunk (best first).

    Returns:
        List of PlagiarismMatch sorted by containment_score descending.
    """
    # Pre-compute reference fingerprints once
    ref_fps: list[tuple[dict, set[int]]] = []
    for rc in ref_chunks:
        fp = ngram_fingerprint(rc["content"], n=n)
        if fp:
            ref_fps.append((rc, fp))

    if not ref_fps:
        logger.warning("No reference chunks with n-gram fingerprints")
        return []

    matches: list[PlagiarismMatch] = []

    for dc in doc_chunks:
        dc_fp = ngram_fingerprint(dc["content"], n=n)
        if not dc_fp:
            continue

        chunk_matches: list[PlagiarismMatch] = []

        for rc, rc_fp in ref_fps:
            jacc = jaccard_similarity(dc_fp, rc_fp)
            cont = containment_score(dc_fp, rc_fp)

            if jacc < min_jaccard and cont < min_containment:
                continue

            # Find the actual matched n-gram strings for display
            dc_ngrams = set(extract_ngrams(dc["content"], n=n))
            rc_ngrams = set(extract_ngrams(rc["content"], n=n))
            matched = sorted(dc_ngrams & rc_ngrams)

            chunk_matches.append(PlagiarismMatch(
                upload_chunk_id=str(dc["id"]),
                upload_chunk_index=dc["chunk_index"],
                upload_content=dc["content"],
                reference_chunk_id=str(rc["id"]),
                reference_chunk_index=rc["chunk_index"],
                reference_content=rc["content"],
                jaccard_score=round(jacc, 4),
                containment_score=round(cont, 4),
                matched_ngrams=matched[:20],  # cap for readability
            ))

        # Keep top matches by containment
        chunk_matches.sort(key=lambda m: m.containment_score, reverse=True)
        matches.extend(chunk_matches[:max_matches_per_chunk])

    # Global sort by containment descending
    matches.sort(key=lambda m: m.containment_score, reverse=True)

    logger.info(
        "Plagiarism detection: %d doc chunks × %d ref chunks → %d matches (n=%d)",
        len(doc_chunks), len(ref_fps), len(matches), n,
    )
    return matches
