"""Modular document processing pipeline for plagiarism detection.

Provides step functions for each stage of the pipeline:
  1. Load document
  2. Extract text + images
  3. Chunk text
  4. Generate embeddings (text + images)
  5. Run detection methods
  6. Compute score
  7. Save report and matches

Each step is independently callable with proper logging and error handling.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path
from typing import Callable
from uuid import UUID

from app.core.chunker import chunk_text
from app.core.embedding import encode_texts
from app.core.pdf import extract_pdf
from app.core.plagiarism import detect_plagiarism as _detect_plagiarism
from app.core.scoring import compute_report_score

logger = logging.getLogger(__name__)


# ── Error handling decorator ───────────────────────────────────────────────


def pipeline_step(step_name: str):
    """Decorator for pipeline steps to add consistent logging and error handling."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger.info("Pipeline step '%s' started", step_name)
            try:
                result = func(*args, **kwargs)
                logger.info("Pipeline step '%s' completed successfully", step_name)
                return result
            except Exception as exc:
                logger.error("Pipeline step '%s' failed: %s", step_name, exc, exc_info=True)
                raise
        return wrapper
    return decorator


# ── Step 1: Load document ───────────────────────────────────────────────

@pipeline_step("load_document")
def load_document(document_id: UUID, file_path: Path) -> dict:
    """Load document metadata and verify file exists.

    Returns:
        Dict with document_id, file_path, file_size, exists.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Document file not found: {file_path}")

    file_size = file_path.stat().st_size
    logger.info("Loaded document %s: %s (%d bytes)", document_id, file_path, file_size)

    return {
        "document_id": str(document_id),
        "file_path": str(file_path),
        "file_size": file_size,
        "exists": True,
    }


# ── Step 2: Extract text + images ────────────────────────────────────────

@pipeline_step("extract_content")
def extract_content(file_path: Path, *, extract_images: bool = True) -> dict:
    """Extract text and optionally images from PDF.

    Args:
        file_path: Path to PDF file.
        extract_images: Whether to extract images (default True).

    Returns:
        Dict with text, page_count, pages, images, metadata.
    """
    extraction = extract_pdf(file_path, extract_images=extract_images, image_include_b64=False)

    logger.info(
        "Extracted %d pages, %d chars, %d images from %s",
        extraction.page_count,
        len(extraction.text),
        len(extraction.images),
        file_path,
    )

    return {
        "text": extraction.text,
        "page_count": extraction.page_count,
        "pages": extraction.pages,
        "images": [
            {
                "page_number": img.page_number,
                "image_index": img.image_index,
                "width": img.width,
                "height": img.height,
                "format": img.format,
                "size_bytes": img.size_bytes,
            }
            for img in extraction.images
        ],
        "metadata": extraction.metadata,
    }


# ── Step 3: Chunk text ─────────────────────────────────────────────────

@pipeline_step("chunk_document_text")
def chunk_document_text(text: str, *, strategy: str = "paragraph", max_tokens: int = 256) -> dict:
    """Split extracted text into embedding-ready chunks.

    Args:
        text: Full document text.
        strategy: "paragraph" or "sentence".
        max_tokens: Maximum tokens per chunk.

    Returns:
        Dict with chunks list and chunk_count.
    """
    chunks = chunk_text(text, strategy=strategy, max_tokens=max_tokens)

    logger.info("Chunked text into %d chunks (strategy=%s)", len(chunks), strategy)

    return {
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "content": c.content,
                "token_count": c.token_count,
                "char_count": c.char_count,
            }
            for c in chunks
        ],
        "chunk_count": len(chunks),
    }


# ── Step 4: Generate text embeddings ─────────────────────────────────

@pipeline_step("generate_text_embeddings")
def generate_text_embeddings(chunks: list[dict], *, batch_size: int = 64) -> dict:
    """Generate embedding vectors for text chunks.

    Args:
        chunks: List of chunk dicts with 'content' field.
        batch_size: Batch size for encoding.

    Returns:
        Dict with embeddings list and embedding dimension.
    """
    texts = [c["content"] for c in chunks]
    vectors = encode_texts(texts, batch_size=batch_size)

    logger.info("Generated %d text embeddings (batch_size=%d)", len(vectors), batch_size)

    return {
        "embeddings": vectors,
        "dimension": len(vectors[0]) if vectors else 0,
    }


# ── Step 5: Detection methods ─────────────────────────────────────────

def run_plagiarism_detection(
    doc_chunks: list[dict],
    ref_chunks: list[dict],
    *,
    n: int = 7,
    min_jaccard: float = 0.1,
    min_containment: float = 0.2,
) -> dict:
    """Run direct plagiarism detection via n-gram matching.

    Args:
        doc_chunks: List of document chunk dicts.
        ref_chunks: List of reference chunk dicts.
        n: N-gram size.
        min_jaccard: Minimum Jaccard similarity.
        min_containment: Minimum containment score.

    Returns:
        Dict with matches list and match_count.
    """
    matches = _detect_plagiarism(
        doc_chunks,
        ref_chunks,
        n=n,
        min_jaccard=min_jaccard,
        min_containment=min_containment,
    )

    logger.info("Plagiarism detection: %d matches", len(matches))

    return {
        "matches": [
            {
                "upload_chunk_id": m.upload_chunk_id,
                "upload_chunk_index": m.upload_chunk_index,
                "upload_content": m.upload_content,
                "reference_chunk_id": m.reference_chunk_id,
                "reference_chunk_index": m.reference_chunk_index,
                "reference_content": m.reference_content,
                "jaccard_score": m.jaccard_score,
                "containment_score": m.containment_score,
                "matched_ngrams": m.matched_ngrams,
            }
            for m in matches
        ],
        "match_count": len(matches),
    }


def run_semantic_similarity(
    doc_embeddings: list[list[float]],
    ref_embeddings: list[list[float]],
    *,
    threshold: float = 0.3,
    top_k: int = 10,
) -> dict:
    """Run semantic similarity detection (placeholder).

    In production, this would use the batch RPC for pgvector search.
    For now, this is a stub that returns cosine similarity between embeddings.

    Args:
        doc_embeddings: List of document embedding vectors.
        ref_embeddings: List of reference embedding vectors.
        threshold: Minimum similarity to report.
        top_k: Max matches per doc chunk.

    Returns:
        Dict with matches list and match_count.
    """
    # Stub implementation - in production use ChunkService.match_chunks_batch
    matches = []
    for i, doc_emb in enumerate(doc_embeddings):
        for j, ref_emb in enumerate(ref_embeddings):
            # Simple cosine similarity
            import numpy as np
            sim = float(np.dot(doc_emb, ref_emb) / (np.linalg.norm(doc_emb) * np.linalg.norm(ref_emb)))
            if sim >= threshold:
                matches.append({
                    "upload_chunk_index": i,
                    "reference_chunk_index": j,
                    "similarity": round(sim, 4),
                })

    matches.sort(key=lambda m: m["similarity"], reverse=True)
    logger.info("Semantic similarity: %d matches", len(matches))

    return {
        "matches": matches[:top_k],
        "match_count": len(matches),
    }


def run_paraphrase_detection(
    doc_embeddings: list[list[float]],
    ref_embeddings: list[list[float]],
    *,
    min_similarity: float = 0.55,
    max_similarity: float = 0.90,
) -> dict:
    """Run paraphrase detection (placeholder).

    In production, this would use the paraphrase zone filtering on semantic results.

    Args:
        doc_embeddings: List of document embedding vectors.
        ref_embeddings: List of reference embedding vectors.
        min_similarity: Lower bound for paraphrase zone.
        max_similarity: Upper bound (exclude near-exact copies).

    Returns:
        Dict with matches list and match_count.
    """
    # Stub implementation - in production use ChunkService.detect_paraphrases
    matches = []
    for i, doc_emb in enumerate(doc_embeddings):
        for j, ref_emb in enumerate(ref_embeddings):
            import numpy as np
            sim = float(np.dot(doc_emb, ref_emb) / (np.linalg.norm(doc_emb) * np.linalg.norm(ref_emb)))
            if min_similarity <= sim < max_similarity:
                matches.append({
                    "upload_chunk_index": i,
                    "reference_chunk_index": j,
                    "similarity": round(sim, 4),
                })

    matches.sort(key=lambda m: m["similarity"], reverse=True)
    logger.info("Paraphrase detection: %d matches", len(matches))

    return {
        "matches": matches,
        "match_count": len(matches),
    }


def run_image_similarity(
    doc_images: list[dict],
    ref_images: list[dict],
    *,
    threshold: float = 0.5,
) -> dict:
    """Run image similarity detection using CLIP embeddings.

    Args:
        doc_images: List of document image metadata dicts.
        ref_images: List of reference image metadata dicts.
        threshold: Minimum similarity to report.

    Returns:
        Dict with matches list and match_count.
    """
    from app.core.image_embedding import encode_images_batch, compute_image_similarity

    # Extract image paths from metadata (assuming they're stored somewhere accessible)
    # For now, this is a stub - in production, images would be stored and paths provided
    logger.info("Image similarity: %d doc images, %d ref images", len(doc_images), len(ref_images))

    # Stub: return no matches until image storage is implemented
    return {
        "matches": [],
        "match_count": 0,
    }


# ── Step 6: Compute score ──────────────────────────────────────────────

@pipeline_step("compute_detection_score")
def compute_detection_score(
    plagiarism_matches: list[dict],
    paraphrase_matches: list[dict],
    semantic_matches: list[dict],
    image_matches: list[dict] | None = None,
) -> dict:
    """Compute weighted final score from all detection methods.

    Args:
        plagiarism_matches: List of plagiarism match dicts.
        paraphrase_matches: List of paraphrase match dicts.
        semantic_matches: List of semantic match dicts.
        image_matches: Optional list of image match dicts.

    Returns:
        Dict with ScoreBreakdown.to_dict() result.
    """
    score_breakdown = compute_report_score(
        plagiarism_matches=plagiarism_matches,
        paraphrase_matches=paraphrase_matches,
        semantic_matches=semantic_matches,
    )

    logger.info("Final score: %.4f", score_breakdown.final_score)

    return score_breakdown.to_dict()


# ── Step 7: Save report and matches ────────────────────────────────────

@pipeline_step("save_report_and_matches")
def save_report_and_matches(
    report_id: UUID,
    score_breakdown: dict,
    all_matches: list[dict],
    db,
) -> dict:
    """Save report score and matches to database.

    Args:
        report_id: Report UUID.
        score_breakdown: Score breakdown dict from compute_detection_score.
        all_matches: Combined list of all match dicts.
        db: Database instance.

    Returns:
        Dict with report_id, total_matches, and breakdown.
    """
    from app.services.report_service import ReportService

    report_svc = ReportService(db)

    # Update report with score and breakdown
    report_svc.update_report(
        report_id,
        status="completed",
        overall_score=score_breakdown["final_score"],
        total_matches=len(all_matches),
        score_breakdown=score_breakdown,
    )

    # Clear old matches and store new ones
    report_svc._match_repo.delete_by_report(report_id)
    for m in all_matches:
        report_svc.add_match(
            upload_chunk_id=UUID(m["upload_chunk_id"]),
            reference_chunk_id=UUID(m["reference_chunk_id"]),
            similarity_score=m.get("similarity_score", m.get("containment_score", 0.0)),
            report_id=report_id,
        )

    logger.info("Saved report %s with %d matches", report_id, len(all_matches))

    return {
        "report_id": str(report_id),
        "total_matches": len(all_matches),
        "score_breakdown": score_breakdown,
    }


# ── Pipeline orchestrator ───────────────────────────────────────────────

def run_full_pipeline(
    document_id: UUID,
    file_path: Path,
    report_id: UUID,
    ref_chunks: list[dict],
    ref_embeddings: list[list[float]],
    ref_images: list[dict],
    db,
) -> dict:
    """Run the complete plagiarism detection pipeline.

    Executes all steps in order with error handling and logging.

    Args:
        document_id: Document UUID.
        file_path: Path to PDF file.
        report_id: Report UUID.
        ref_chunks: Reference chunks for comparison.
        ref_embeddings: Reference embeddings for similarity search.
        ref_images: Reference images for image similarity.
        db: Database instance.

    Returns:
        Dict with pipeline results including score breakdown and matches.
    """
    try:
        # Step 1: Load
        load_result = load_document(document_id, file_path)

        # Step 2: Extract
        extract_result = extract_content(file_path, extract_images=True)

        # Step 3: Chunk
        chunk_result = chunk_document_text(extract_result["text"])

        # Step 4: Embeddings (text only for now)
        embed_result = generate_text_embeddings(chunk_result["chunks"])

        # Step 5: Detection
        plagiarism_result = run_plagiarism_detection(
            chunk_result["chunks"],
            ref_chunks,
        )

        semantic_result = run_semantic_similarity(
            embed_result["embeddings"],
            ref_embeddings,
        )

        paraphrase_result = run_paraphrase_detection(
            embed_result["embeddings"],
            ref_embeddings,
        )

        image_result = run_image_similarity(
            extract_result["images"],
            ref_images,
        )

        # Step 6: Score
        score_result = compute_detection_score(
            plagiarism_result["matches"],
            paraphrase_result["matches"],
            semantic_result["matches"],
            image_result["matches"],
        )

        # Step 7: Save
        all_matches = (
            plagiarism_result["matches"]
            + paraphrase_result["matches"]
            + semantic_result["matches"]
            + image_result["matches"]
        )
        save_result = save_report_and_matches(
            report_id,
            score_result,
            all_matches,
            db,
        )

        return {
            "status": "completed",
            "document_id": str(document_id),
            "report_id": str(report_id),
            "steps": {
                "load": load_result,
                "extract": extract_result,
                "chunk": chunk_result,
                "embed": embed_result,
                "plagiarism": plagiarism_result,
                "semantic": semantic_result,
                "paraphrase": paraphrase_result,
                "image": image_result,
                "score": score_result,
                "save": save_result,
            },
        }

    except Exception as exc:
        logger.exception("Pipeline failed for document %s", document_id)
        raise
