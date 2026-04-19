"""Tests for the scoring system."""

from app.core.scoring import (
    ScoreBreakdown,
    compute_report_score,
    compute_match_score,
    SCORING_WEIGHTS,
)


class TestScoringWeights:
    def test_weights_sum_to_one(self):
        total = sum(SCORING_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6

    def test_weights_are_positive(self):
        for k, v in SCORING_WEIGHTS.items():
            assert v > 0, f"Weight {k} must be positive"


class TestComputeMatchScore:
    def test_all_components_present(self):
        score = compute_match_score(
            plagiarism_score=0.8,
            paraphrase_score=0.7,
            semantic_score=0.5,
        )
        assert 0.0 <= score <= 1.0

    def test_only_plagiarism(self):
        score = compute_match_score(
            plagiarism_score=0.8,
            paraphrase_score=0.0,
            semantic_score=0.0,
        )
        assert score == 0.8

    def test_only_paraphrase(self):
        score = compute_match_score(
            plagiarism_score=0.0,
            paraphrase_score=0.7,
            semantic_score=0.0,
        )
        assert score == 0.7

    def test_only_semantic(self):
        score = compute_match_score(
            plagiarism_score=0.0,
            paraphrase_score=0.0,
            semantic_score=0.5,
        )
        assert score == 0.5

    def test_all_zero(self):
        score = compute_match_score(
            plagiarism_score=0.0,
            paraphrase_score=0.0,
            semantic_score=0.0,
        )
        assert score == 0.0

    def test_custom_weights(self):
        custom = {"plagiarism": 0.5, "paraphrase": 0.5, "semantic": 0.0}
        score = compute_match_score(
            plagiarism_score=0.8,
            paraphrase_score=0.6,
            semantic_score=0.0,
            weights=custom,
        )
        expected = 0.5 * 0.8 + 0.5 * 0.6
        assert abs(score - expected) < 1e-6


class TestComputeReportScore:
    def test_all_categories_present(self):
        plagiarism = [{"containment_score": 0.8}, {"containment_score": 0.7}]
        paraphrase = [{"similarity": 0.6}, {"similarity": 0.5}]
        semantic = [{"similarity": 0.4}, {"similarity": 0.3}]

        breakdown = compute_report_score(plagiarism, paraphrase, semantic)

        assert isinstance(breakdown, ScoreBreakdown)
        assert 0.0 <= breakdown.final_score <= 1.0
        assert breakdown.plagiarism_score > 0
        assert breakdown.paraphrase_score > 0
        assert breakdown.semantic_score > 0
        assert breakdown.match_counts["plagiarism"] == 2
        assert breakdown.match_counts["paraphrase"] == 2
        assert breakdown.match_counts["semantic"] == 2

    def test_empty_matches(self):
        breakdown = compute_report_score([], [], [])
        assert breakdown.final_score == 0.0
        assert breakdown.plagiarism_score == 0.0
        assert breakdown.paraphrase_score == 0.0
        assert breakdown.semantic_score == 0.0
        assert breakdown.match_counts["plagiarism"] == 0
        assert breakdown.match_counts["paraphrase"] == 0
        assert breakdown.match_counts["semantic"] == 0

    def test_only_plagiarism(self):
        plagiarism = [{"containment_score": 0.9}, {"containment_score": 0.7}]
        breakdown = compute_report_score(plagiarism, [], [])
        assert breakdown.final_score > 0
        assert breakdown.plagiarism_score > 0
        assert breakdown.paraphrase_score == 0.0
        assert breakdown.semantic_score == 0.0

    def test_top_n_averaging(self):
        # With 10 matches, should only average top 5
        plagiarism = [{"containment_score": i / 10} for i in range(1, 11)]
        breakdown = compute_report_score(plagiarism, [], [])
        # Top 5 are 0.6, 0.7, 0.8, 0.9, 1.0 → avg = 0.8
        assert abs(breakdown.plagiarism_score - 0.8) < 1e-6

    def test_custom_weights(self):
        custom = {"plagiarism": 1.0, "paraphrase": 0.0, "semantic": 0.0}
        plagiarism = [{"containment_score": 0.8}]
        breakdown = compute_report_score(plagiarism, [], [], weights=custom)
        assert breakdown.final_score == 0.8


class TestScoreBreakdown:
    def test_to_dict_structure(self):
        breakdown = ScoreBreakdown(
            final_score=0.75,
            plagiarism_score=0.8,
            paraphrase_score=0.6,
            semantic_score=0.4,
            weights={"plagiarism": 0.6, "paraphrase": 0.3, "semantic": 0.1},
            match_counts={"plagiarism": 5, "paraphrase": 3, "semantic": 2},
        )
        d = breakdown.to_dict()
        assert "final_score" in d
        assert "breakdown" in d
        assert d["breakdown"]["plagiarism"]["score"] == 0.8
        assert d["breakdown"]["plagiarism"]["weight"] == 0.6
        assert d["breakdown"]["plagiarism"]["match_count"] == 5

    def test_to_dict_rounding(self):
        breakdown = ScoreBreakdown(
            final_score=0.123456789,
            plagiarism_score=0.987654321,
            paraphrase_score=0.456789123,
            semantic_score=0.321654987,
            weights={"plagiarism": 0.6, "paraphrase": 0.3, "semantic": 0.1},
            match_counts={"plagiarism": 1, "paraphrase": 1, "semantic": 1},
        )
        d = breakdown.to_dict()
        assert d["final_score"] == 0.1235  # rounded to 4 decimals
        assert d["breakdown"]["plagiarism"]["score"] == 0.9877
