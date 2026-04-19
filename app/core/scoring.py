"""Scoring system for plagiarism detection reports.

Computes a weighted final score from three detection methods:
  - Direct plagiarism (n-gram matching)
  - Paraphrase detection (embedding similarity)
  - Semantic similarity (embedding similarity, lower threshold)

Formula:
  final_score = w1 * direct + w2 * paraphrase + w3 * semantic

Weights are configurable via environment variables.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings


# ── Configurable weights (from env or defaults) ────────────────────────

SCORING_WEIGHTS = {
    "plagiarism": getattr(settings, "scoring_weight_plagiarism", 0.6),
    "paraphrase": getattr(settings, "scoring_weight_paraphrase", 0.3),
    "semantic": getattr(settings, "scoring_weight_semantic", 0.1),
}

# Normalize to sum to 1.0
total_weight = sum(SCORING_WEIGHTS.values())
if total_weight == 0:
    raise ValueError("Scoring weights cannot all be zero")
for key in SCORING_WEIGHTS:
    SCORING_WEIGHTS[key] /= total_weight


# ── Score breakdown dataclass ───────────────────────────────────────────


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of the scoring computation."""

    final_score: float
    plagiarism_score: float
    paraphrase_score: float
    semantic_score: float
    weights: dict[str, float]
    match_counts: dict[str, int]

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "final_score": round(self.final_score, 4),
            "breakdown": {
                "plagiarism": {
                    "score": round(self.plagiarism_score, 4),
                    "weight": round(self.weights["plagiarism"], 4),
                    "match_count": self.match_counts["plagiarism"],
                },
                "paraphrase": {
                    "score": round(self.paraphrase_score, 4),
                    "weight": round(self.weights["paraphrase"], 4),
                    "match_count": self.match_counts["paraphrase"],
                },
                "semantic": {
                    "score": round(self.semantic_score, 4),
                    "weight": round(self.weights["semantic"], 4),
                    "match_count": self.match_counts["semantic"],
                },
            },
        }


# ── Scoring functions ───────────────────────────────────────────────────


def compute_report_score(
    plagiarism_matches: list[dict],
    paraphrase_matches: list[dict],
    semantic_matches: list[dict],
    weights: dict[str, float] | None = None,
) -> ScoreBreakdown:
    """Compute the final report score from match results.

    Args:
        plagiarism_matches: List of plagiarism match dicts with 'containment_score'.
        paraphrase_matches: List of paraphrase match dicts with 'similarity'.
        semantic_matches: List of semantic match dicts with 'similarity'.
        weights: Optional custom weights dict (keys: plagiarism, paraphrase, semantic).

    Returns:
        ScoreBreakdown with final score, component scores, weights, and match counts.
    """
    w = weights or SCORING_WEIGHTS

    # Extract scores from matches
    plagiarism_scores = [m.get("containment_score", 0.0) for m in plagiarism_matches]
    paraphrase_scores = [m.get("similarity", 0.0) for m in paraphrase_matches]
    semantic_scores = [m.get("similarity", 0.0) for m in semantic_matches]

    # Component scores: mean of top-5 matches per category (or all if fewer)
    def _mean_top_n(scores: list[float], n: int = 5) -> float:
        if not scores:
            return 0.0
        top = sorted(scores, reverse=True)[:n]
        return sum(top) / len(top)

    plagiarism_component = _mean_top_n(plagiarism_scores)
    paraphrase_component = _mean_top_n(paraphrase_scores)
    semantic_component = _mean_top_n(semantic_scores)

    # Weighted final score
    final = (
        w["plagiarism"] * plagiarism_component
        + w["paraphrase"] * paraphrase_component
        + w["semantic"] * semantic_component
    )

    return ScoreBreakdown(
        final_score=final,
        plagiarism_score=plagiarism_component,
        paraphrase_score=paraphrase_component,
        semantic_score=semantic_component,
        weights=w.copy(),
        match_counts={
            "plagiarism": len(plagiarism_matches),
            "paraphrase": len(paraphrase_matches),
            "semantic": len(semantic_matches),
        },
    )


def compute_match_score(
    plagiarism_score: float,
    paraphrase_score: float,
    semantic_score: float,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute a weighted score for a single match.

    Used when storing individual match similarity scores in the DB.
    Only includes non-zero components.

    Args:
        plagiarism_score: Containment score from plagiarism detection.
        paraphrase_score: Similarity score from paraphrase detection.
        semantic_score: Similarity score from semantic search.
        weights: Optional custom weights.

    Returns:
        Weighted combined score (0–1).
    """
    w = weights or SCORING_WEIGHTS

    components = []
    if plagiarism_score > 0:
        components.append(("plagiarism", plagiarism_score))
    if paraphrase_score > 0:
        components.append(("paraphrase", paraphrase_score))
    if semantic_score > 0:
        components.append(("semantic", semantic_score))

    if not components:
        return 0.0

    # Renormalize weights for active components only
    active_weight_sum = sum(w[k] for k, _ in components)
    if active_weight_sum == 0:
        return 0.0

    combined = sum(w[k] * v for k, v in components) / active_weight_sum
    return combined
