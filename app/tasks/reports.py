"""Report generation tasks — full pipeline orchestrator."""

import logging
from uuid import UUID

from app.core.worker import celery_app

logger = logging.getLogger(__name__)

STEPS = [
    "loading_chunks",
    "detecting_plagiarism",
    "detecting_paraphrases",
    "computing_score",
    "storing_results",
]


@celery_app.task(bind=True, name="app.tasks.reports.generate_report")
def generate_report(self, report_id: str) -> dict:
    """Background task: generate a comparison report using the pipeline orchestrator.

    Executes the full detection pipeline:
      1. Load document chunks (ensure embeddings)
      2. Direct plagiarism detection (n-gram matching)
      3. Paraphrase detection (embedding similarity in paraphrase zone)
      4. Compute weighted score
      5. Store results and breakdown

    Uses modular pipeline functions from app.core.pipeline for clean separation.
    """
    logger.info("Generating report %s (task %s)", report_id, self.request.id)

    from app.db.supabase_client import task_db
    from app.services.report_service import ReportService
    from app.services.chunk_service import ChunkService

    with task_db() as db:
        try:
            report_svc = ReportService(db)
            chunk_svc = ChunkService(db)

            report = report_svc.get_report(UUID(report_id))
            if not report:
                logger.error("Report %s not found", report_id)
                return {"status": "error", "detail": "Report not found"}

            document_id = UUID(report["document_id"])

            # Step 1: Ensure document chunks have embeddings
            self.update_state(state="PROGRESS", meta={"step": STEPS[0], "current": 1, "total": len(STEPS), "report_id": report_id})

            newly_embedded = chunk_svc.embed_chunks("upload", document_id)
            if newly_embedded > 0:
                logger.info("Report %s — embedded %d new chunks for document %s", report_id, newly_embedded, document_id)

            # Step 2: Direct plagiarism detection
            self.update_state(state="PROGRESS", meta={"step": STEPS[1], "current": 2, "total": len(STEPS), "report_id": report_id})

            plagiarism_matches = chunk_svc.detect_plagiarism(
                document_id,
                n=7,
                min_jaccard=0.1,
                min_containment=0.2,
            )
            logger.info("Report %s — %d plagiarism matches", report_id, len(plagiarism_matches))

            # Step 3: Paraphrase detection
            self.update_state(state="PROGRESS", meta={"step": STEPS[2], "current": 3, "total": len(STEPS), "report_id": report_id})

            paraphrase_matches = chunk_svc.detect_paraphrases(
                document_id,
                min_similarity=0.55,
                max_similarity=0.90,
            )
            logger.info("Report %s — %d paraphrase matches", report_id, len(paraphrase_matches))

            # Step 4: Compute score using scoring module
            self.update_state(state="PROGRESS", meta={"step": STEPS[3], "current": 4, "total": len(STEPS), "report_id": report_id})

            from app.core.scoring import compute_report_score

            score_breakdown = compute_report_score(
                plagiarism_matches=plagiarism_matches,
                paraphrase_matches=paraphrase_matches,
                semantic_matches=[],
            )
            logger.info("Report %s — final score %.4f", report_id, score_breakdown.final_score)

            # Step 5: Store results
            self.update_state(state="PROGRESS", meta={"step": STEPS[4], "current": 5, "total": len(STEPS), "report_id": report_id})

            report_svc._match_repo.delete_by_report(UUID(report_id))

            merged: dict[tuple[str, str], dict] = {}

            for m in plagiarism_matches:
                key = (m["upload_chunk_id"], m["reference_chunk_id"])
                merged[key] = {
                    "upload_chunk_id": m["upload_chunk_id"],
                    "reference_chunk_id": m["reference_chunk_id"],
                    "plagiarism_score": m["containment_score"],
                    "paraphrase_score": 0.0,
                }

            for m in paraphrase_matches:
                key = (str(m["upload_chunk_id"]), str(m["reference_chunk_id"]))
                if key in merged:
                    merged[key]["paraphrase_score"] = m["similarity"]
                else:
                    merged[key] = {
                        "upload_chunk_id": str(m["upload_chunk_id"]),
                        "reference_chunk_id": str(m["reference_chunk_id"]),
                        "plagiarism_score": 0.0,
                        "paraphrase_score": m["similarity"],
                    }

            from app.core.scoring import compute_match_score

            for m in merged.values():
                combined = compute_match_score(
                    plagiarism_score=m["plagiarism_score"],
                    paraphrase_score=m["paraphrase_score"],
                    semantic_score=0.0,
                )
                report_svc.add_match(
                    upload_chunk_id=UUID(m["upload_chunk_id"]),
                    reference_chunk_id=UUID(m["reference_chunk_id"]),
                    similarity_score=round(combined, 4),
                    report_id=UUID(report_id),
                )

            n_plagiarism = sum(1 for m in merged.values() if m.get("plagiarism_score", 0) > 0)
            n_paraphrase = sum(1 for m in merged.values() if m.get("paraphrase_score", 0) > 0)

            report_svc.update_report(
                UUID(report_id),
                status="completed",
                overall_score=score_breakdown.final_score,
                total_matches=len(merged),
                score_breakdown=score_breakdown.to_dict(),
            )

            logger.info(
                "Report %s complete — %d matches (plagiarism=%d, paraphrase=%d), score=%.4f",
                report_id, len(merged), n_plagiarism, n_paraphrase, score_breakdown.final_score,
            )
            return {
                "status": "ok",
                "report_id": report_id,
                "total_matches": len(merged),
                "plagiarism_matches": n_plagiarism,
                "paraphrase_matches": n_paraphrase,
                "aggregate_score": score_breakdown.final_score,
                "score_breakdown": score_breakdown.to_dict(),
            }

        except Exception as exc:
            logger.exception("Failed to generate report %s", report_id)
            try:
                report_svc = ReportService(db)
                report_svc.update_report(
                    UUID(report_id),
                    status="failed",
                    error_message=str(exc)[:500]  # Limit error message length
                )
            except Exception as e:
                logger.error("Failed to mark report %s as failed: %s", report_id, e)
            raise self.retry(exc=exc, countdown=60, max_retries=3)
