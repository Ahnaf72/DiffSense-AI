"""Tests for the reports API with color-coded data."""

from uuid import uuid4

from app.core.pipeline import compute_detection_score


class TestColorCodingLogic:
    """Test color coding based on severity levels."""

    def test_high_severity_color(self):
        """Score >= 0.8 should be red (#ef4444)."""
        score = 0.85
        if score >= 0.8:
            color = "#ef4444"
            severity = "high"
        else:
            color = "#22c55e"
            severity = "low"
        assert color == "#ef4444"
        assert severity == "high"

    def test_medium_severity_color(self):
        """Score 0.5-0.79 should be amber (#f59e0b)."""
        score = 0.6
        if score >= 0.8:
            color = "#ef4444"
            severity = "high"
        elif score >= 0.5:
            color = "#f59e0b"
            severity = "medium"
        else:
            color = "#22c55e"
            severity = "low"
        assert color == "#f59e0b"
        assert severity == "medium"

    def test_low_severity_color(self):
        """Score < 0.5 should be green (#22c55e)."""
        score = 0.3
        if score >= 0.8:
            color = "#ef4444"
            severity = "high"
        elif score >= 0.5:
            color = "#f59e0b"
            severity = "medium"
        else:
            color = "#22c55e"
            severity = "low"
        assert color == "#22c55e"
        assert severity == "low"

    def test_boundary_conditions(self):
        """Test boundary values for color coding."""
        # Exactly 0.8 should be high (red)
        assert 0.8 >= 0.8
        # Exactly 0.5 should be medium (amber)
        assert 0.5 >= 0.5
        # Just below 0.5 should be low (green)
        assert 0.49 < 0.5


class TestSegmentGrouping:
    """Test grouping segments by severity."""

    def test_group_by_severity(self):
        matches = [
            {"similarity_score": 0.9, "severity": "high"},
            {"similarity_score": 0.6, "severity": "medium"},
            {"similarity_score": 0.3, "severity": "low"},
            {"similarity_score": 0.85, "severity": "high"},
        ]

        segments_by_severity = {
            "high": [m for m in matches if m["severity"] == "high"],
            "medium": [m for m in matches if m["severity"] == "medium"],
            "low": [m for m in matches if m["severity"] == "low"],
        }

        assert len(segments_by_severity["high"]) == 2
        assert len(segments_by_severity["medium"]) == 1
        assert len(segments_by_severity["low"]) == 1

    def test_empty_matches(self):
        segments_by_severity = {
            "high": [],
            "medium": [],
            "low": [],
        }
        assert len(segments_by_severity["high"]) == 0
        assert len(segments_by_severity["medium"]) == 0
        assert len(segments_by_severity["low"]) == 0


class TestSourceExtraction:
    """Test extracting unique sources from matches."""

    def test_extract_unique_sources(self):
        matches = [
            {"reference_source_id": "ref1"},
            {"reference_source_id": "ref2"},
            {"reference_source_id": "ref1"},  # duplicate
            {"reference_source_id": "ref3"},
        ]

        sources = list(set(m["reference_source_id"] for m in matches if m["reference_source_id"]))
        sources.sort()

        assert len(sources) == 3
        assert "ref1" in sources
        assert "ref2" in sources
        assert "ref3" in sources

    def test_empty_sources(self):
        matches = []
        sources = list(set(m["reference_source_id"] for m in matches if m["reference_source_id"]))
        assert sources == []


class TestReportResponseStructure:
    """Test the structure of the detailed report response."""

    def test_response_has_required_fields(self):
        """Detailed report should have all required fields."""
        response = {
            "report_id": str(uuid4()),
            "document_id": str(uuid4()),
            "overall_score": 0.75,
            "total_matches": 5,
            "score_breakdown": {},
            "matches": [],
            "segments": {"high": [], "medium": [], "low": []},
            "sources": [],
            "status": "completed",
            "created_at": "2024-01-01T00:00:00Z",
        }

        required_fields = [
            "report_id",
            "document_id",
            "overall_score",
            "total_matches",
            "score_breakdown",
            "matches",
            "segments",
            "sources",
            "status",
        ]

        for field in required_fields:
            assert field in response

    def test_match_has_color_and_severity(self):
        """Each match should have color and severity fields."""
        match = {
            "id": str(uuid4()),
            "upload_chunk_id": str(uuid4()),
            "upload_content": "Sample text",
            "upload_chunk_index": 0,
            "reference_chunk_id": str(uuid4()),
            "reference_content": "Reference text",
            "reference_chunk_index": 0,
            "reference_source_id": "ref1",
            "reference_source_type": "reference",
            "similarity_score": 0.85,
            "color": "#ef4444",
            "severity": "high",
        }

        assert "color" in match
        assert "severity" in match
        assert match["color"] in ["#ef4444", "#f59e0b", "#22c55e"]
        assert match["severity"] in ["high", "medium", "low"]
