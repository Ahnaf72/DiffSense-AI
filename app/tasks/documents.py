"""Document processing tasks — extract, chunk, embed, store."""

import logging
from pathlib import Path
from uuid import UUID

from app.core.worker import celery_app

logger = logging.getLogger(__name__)

STEPS = ["extracting_text", "splitting_chunks", "generating_embeddings", "storing_chunks"]


@celery_app.task(bind=True, name="app.tasks.documents.process_upload")
def process_upload(self, doc_id: str) -> dict:
    """Background task: process an uploaded PDF through the full pipeline.

    Steps:
      1. Extract text from PDF
      2. Split into chunks
      3. Generate embeddings (batched)
      4. Store chunks + vectors in DB
    """
    logger.info("Processing document %s (task %s)", doc_id, self.request.id)

    from app.db.supabase_client import task_db
    from app.services.document_service import DocumentService
    from app.services.chunk_service import ChunkService

    with task_db() as db:
        try:
            doc_svc = DocumentService(db)
            chunk_svc = ChunkService(db)

            doc = doc_svc.get_document(UUID(doc_id))
            if not doc:
                logger.error("Document %s not found", doc_id)
                return {"status": "error", "detail": "Document not found"}

            # Note: status is already set to 'processing' by the route's try_mark_processing

            # Step 1: Extract text
            self.update_state(state="PROGRESS", meta={"step": STEPS[0], "current": 1, "total": len(STEPS), "doc_id": doc_id})

            from app.core.pdf import extract_pdf
            from app.core.config import settings

            file_path = Path(settings.upload_dir) / doc["file_path"]
            extraction = extract_pdf(file_path, extract_images=False)
            logger.info("Document %s — extracted %d chars from %d pages", doc_id, len(extraction.text), extraction.page_count)

            # Step 2: Split into chunks
            self.update_state(state="PROGRESS", meta={"step": STEPS[1], "current": 2, "total": len(STEPS), "doc_id": doc_id})

            from app.core.chunker import chunk_text
            chunks = chunk_text(extraction.text, strategy="paragraph", max_tokens=256, overlap_tokens=32)
            logger.info("Document %s — split into %d chunks", doc_id, len(chunks))

            # Step 3+4: Generate embeddings (batched) and store chunks + vectors
            self.update_state(state="PROGRESS", meta={"step": STEPS[2], "current": 3, "total": len(STEPS), "doc_id": doc_id})

            from app.core.embedding import encode_texts

            chunk_dicts = [{"chunk_index": c.chunk_index, "content": c.content, "token_count": c.token_count} for c in chunks]
            texts = [c.content for c in chunks]

            # Batched encoding — 64 texts per forward pass
            vectors = encode_texts(texts, batch_size=64)
            logger.info("Document %s — generated %d embeddings (batched)", doc_id, len(vectors))

            self.update_state(state="PROGRESS", meta={"step": STEPS[3], "current": 4, "total": len(STEPS), "doc_id": doc_id})

            stored = chunk_svc.store_chunks_with_embeddings(
                source_type="upload",
                source_id=UUID(doc_id),
                chunks=chunk_dicts,
                embeddings=vectors,
                document_id=UUID(doc_id),
            )
            logger.info("Document %s — stored %d chunks with embeddings in DB", doc_id, len(stored))

            doc_svc.mark_ready(UUID(doc_id))
            logger.info("Document %s analysis complete", doc_id)
            return {"status": "ok", "doc_id": doc_id, "steps_completed": len(STEPS), "chunks": len(chunks)}

        except Exception as exc:
            logger.exception("Failed to process document %s", doc_id)
            try:
                doc_svc = DocumentService(db)
                doc_svc.mark_failed(UUID(doc_id))
            except Exception as e:
                logger.error("Failed to mark document %s as failed: %s", doc_id, e)
            raise self.retry(exc=exc, countdown=60, max_retries=3)
