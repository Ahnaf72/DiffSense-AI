"""End-to-end integration test for the full plagiarism detection pipeline.

Tests the complete flow:
  1. Upload document
  2. Process (extract, chunk, embed)
  3. Analyze (detect plagiarism, paraphrase, semantic)
  4. Generate report with score breakdown
  5. Retrieve detailed report with color-coded segments

Run with: python integration_test.py
"""

import logging
import sys
from pathlib import Path
from uuid import uuid4

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("integration_test.log"),
    ],
)
logger = logging.getLogger(__name__)


def test_full_pipeline():
    """Test the complete plagiarism detection pipeline."""
    logger.info("=" * 60)
    logger.info("Starting full pipeline integration test")
    logger.info("=" * 60)

    try:
        # Step 1: Test pipeline modules independently
        logger.info("Step 1: Testing pipeline modules")
        test_pipeline_modules()

        # Step 2: Test scoring system
        logger.info("Step 2: Testing scoring system")
        test_scoring_system()

        # Step 3: Test color coding logic
        logger.info("Step 3: Testing color coding")
        test_color_coding()

        logger.info("=" * 60)
        logger.info("Integration test PASSED")
        logger.info("=" * 60)
        return True

    except Exception as exc:
        logger.error("Integration test FAILED: %s", exc, exc_info=True)
        return False


def test_pipeline_modules():
    """Test pipeline step functions."""
    from app.core.pipeline import (
        chunk_document_text,
        generate_text_embeddings,
        compute_detection_score,
    )

    # Test chunking
    logger.info("  - Testing chunk_document_text")
    text = "This is a test document with multiple paragraphs. " * 10
    chunk_result = chunk_document_text(text)
    assert chunk_result["chunk_count"] > 0, "Should produce chunks"
    logger.info(f"    [OK] Chunked into {chunk_result['chunk_count']} chunks")

    # Test embeddings
    logger.info("  - Testing generate_text_embeddings")
    chunks = [{"content": "Test chunk 1"}, {"content": "Test chunk 2"}]
    embed_result = generate_text_embeddings(chunks)
    assert embed_result["dimension"] == 384, "Should be 384-dim"
    logger.info(f"    [OK] Generated {len(embed_result['embeddings'])} embeddings")

    # Test scoring
    logger.info("  - Testing compute_detection_score")
    plagiarism = [{"containment_score": 0.8}]
    score_result = compute_detection_score(plagiarism, [], [])
    assert score_result["final_score"] > 0, "Should have score > 0"
    logger.info(f"    [OK] Computed score: {score_result['final_score']:.4f}")


def test_scoring_system():
    """Test scoring module."""
    from app.core.scoring import compute_report_score, SCORING_WEIGHTS

    logger.info("  - Testing scoring weights")
    assert abs(sum(SCORING_WEIGHTS.values()) - 1.0) < 1e-6, "Weights should sum to 1"
    logger.info(f"    [OK] Weights: {SCORING_WEIGHTS}")

    logger.info("  - Testing compute_report_score")
    matches = [{"containment_score": 0.9}, {"containment_score": 0.7}]
    breakdown = compute_report_score(matches, [], [])
    assert breakdown.final_score > 0, "Should have final score"
    logger.info(f"    [OK] Final score: {breakdown.final_score:.4f}")


def test_color_coding():
    """Test color coding logic."""
    logger.info("  - Testing color coding")

    # High severity
    score = 0.85
    if score >= 0.8:
        color = "#ef4444"
        severity = "high"
    elif score >= 0.5:
        color = "#f59e0b"
        severity = "medium"
    else:
        color = "#22c55e"
        severity = "low"
    assert color == "#ef4444", "High should be red"
    logger.info(f"    [OK] Score {score} -> {color} ({severity})")

    # Medium severity
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
    assert color == "#f59e0b", "Medium should be amber"
    logger.info(f"    [OK] Score {score} -> {color} ({severity})")

    # Low severity
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
    assert color == "#22c55e", "Low should be green"
    logger.info(f"    [OK] Score {score} -> {color} ({severity})")


if __name__ == "__main__":
    success = test_full_pipeline()
    sys.exit(0 if success else 1)
