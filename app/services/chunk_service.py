"""Service for creating, embedding, and querying text chunks."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from app.db.protocols import Database
from app.repositories.chunk_repo import ChunkRepo

logger = logging.getLogger(__name__)


def _parse_embedding(raw) -> list[float] | None:
    """Safely parse a pgvector embedding value from PostgREST.

    pgvector returns embeddings as strings like '[0.1,0.2,...]' or
    as JSON arrays depending on the driver version.
    """
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


class ChunkService:
    def __init__(self, db: Database) -> None:
        self._repo = ChunkRepo(db)
        self._db = db

    # ── Read ────────────────────────────────────────────────────────

    def list_by_document(self, document_id: UUID) -> list[dict]:
        return self._repo.list_by_source("upload", document_id)

    def list_by_reference(self, reference_id: UUID) -> list[dict]:
        return self._repo.list_by_source("reference", reference_id)

    def get_chunks_without_embeddings(self, source_type: str, source_id: UUID) -> list[dict]:
        """Return chunks that do NOT yet have an embedding stored."""
        all_chunks = self._repo.list_by_source(source_type, source_id)
        return [c for c in all_chunks if c.get("embedding") is None]

    # ── Write ───────────────────────────────────────────────────────

    def create_chunk(
        self,
        source_type: str,
        source_id: UUID,
        chunk_index: int,
        content: str,
        token_count: int = 0,
        document_id: UUID | None = None,
        reference_id: UUID | None = None,
    ) -> dict:
        return self._repo.create(
            source_type=source_type,
            source_id=source_id,
            chunk_index=chunk_index,
            content=content,
            token_count=token_count,
            document_id=document_id,
            reference_id=reference_id,
        )

    def store_embedding(self, chunk_id: UUID, embedding: list[float]) -> None:
        """Store a vector embedding for a chunk via Supabase RPC.

        The embedding must be passed as a string representation of a vector
        because PostgREST serializes JSON arrays as Postgres arrays, not as
        the vector type that pgvector expects.
        """
        self._db.rpc(
            "set_chunk_embedding",
            params={"p_chunk_id": str(chunk_id), "p_embedding": str(embedding)},
        )

    def store_chunks(
        self,
        source_type: str,
        source_id: UUID,
        chunks: list[dict],
        document_id: UUID | None = None,
        reference_id: UUID | None = None,
    ) -> list[dict]:
        """Bulk-store a list of chunk dicts (from chunker) into the DB.

        Each chunk dict must have: chunk_index, content, token_count.
        Returns the list of created DB records.
        """
        # Delete existing chunks for this source first (idempotent)
        self._repo.delete_by_source(source_type, source_id)

        results = []
        for chunk in chunks:
            record = self.create_chunk(
                source_type=source_type,
                source_id=source_id,
                chunk_index=chunk["chunk_index"],
                content=chunk["content"],
                token_count=chunk["token_count"],
                document_id=document_id,
                reference_id=reference_id,
            )
            results.append(record)
        return results

    def store_chunks_with_embeddings(
        self,
        source_type: str,
        source_id: UUID,
        chunks: list[dict],
        embeddings: list[list[float]],
        document_id: UUID | None = None,
        reference_id: UUID | None = None,
    ) -> list[dict]:
        """Store chunks and their embeddings in a single pass.

        Args:
            chunks: List of dicts with chunk_index, content, token_count.
            embeddings: Parallel list of float vectors (same length as chunks).
        """
        stored = self.store_chunks(
            source_type=source_type,
            source_id=source_id,
            chunks=chunks,
            document_id=document_id,
            reference_id=reference_id,
        )

        # Store embeddings via RPC (PostgREST can't handle vector type)
        for record, embedding in zip(stored, embeddings):
            self.store_embedding(UUID(record["id"]), embedding)

        logger.info(
            "Stored %d chunks with embeddings for %s/%s",
            len(stored), source_type, source_id,
        )
        return stored

    def embed_chunks(
        self,
        source_type: str,
        source_id: UUID,
        *,
        batch_size: int = 64,
        force: bool = False,
    ) -> int:
        """Generate and store embeddings for chunks that don't have them yet.

        This is the main entry point for the embedding pipeline. It:
        1. Fetches chunks for the given source
        2. Skips chunks that already have embeddings (unless force=True)
        3. Encodes the remaining texts in batches
        4. Stores each embedding via RPC

        Args:
            source_type: "upload" or "reference"
            source_id: UUID of the document or reference
            batch_size: Number of texts per encoding batch
            force: If True, recompute embeddings even for chunks that have them

        Returns:
            Number of newly embedded chunks.
        """
        if force:
            chunks = self._repo.list_by_source(source_type, source_id)
        else:
            chunks = self.get_chunks_without_embeddings(source_type, source_id)

        if not chunks:
            logger.info("No chunks to embed for %s/%s (all up to date)", source_type, source_id)
            return 0

        texts = [c["content"] for c in chunks]
        logger.info(
            "Embedding %d chunks for %s/%s (batch_size=%d)",
            len(chunks), source_type, source_id, batch_size,
        )

        from app.core.embedding import encode_texts
        vectors = encode_texts(texts, batch_size=batch_size)

        for chunk, vector in zip(chunks, vectors):
            self.store_embedding(UUID(chunk["id"]), vector)

        logger.info(
            "Stored %d embeddings for %s/%s",
            len(vectors), source_type, source_id,
        )
        return len(vectors)

    # ── Similarity search ───────────────────────────────────────────

    def match_chunks(
        self,
        query_embedding: list[float],
        source_type: str = "reference",
        match_threshold: float = 0.5,
        match_count: int = 10,
    ) -> list[dict]:
        """Find similar chunks via single-query vector search (pgvector).

        Uses the HNSW index for fast approximate nearest-neighbor search.
        """
        return self._db.rpc(
            "match_chunks",
            params={
                "p_query_embedding": str(query_embedding),
                "p_source_type": source_type,
                "p_match_threshold": match_threshold,
                "p_match_count": match_count,
            },
        )

    def match_chunks_batch(
        self,
        query_embeddings: list[list[float]],
        source_type: str = "reference",
        match_threshold: float = 0.5,
        match_count: int = 10,
    ) -> dict[int, list[dict]]:
        """Batch vector search — one RPC call for multiple queries.

        Uses the match_chunks_batch RPC to avoid N+1 queries.
        Returns a dict mapping query_index → list of match dicts.

        Args:
            query_embeddings: List of embedding vectors to search for.
            source_type: Filter by source type ("reference" or "upload").
            match_threshold: Minimum cosine similarity.
            match_count: Max results per query.

        Returns:
            Dict mapping query index (0-based) to list of matches.
        """
        if not query_embeddings:
            return {}

        # PostgREST passes arrays as JSON arrays, which become Postgres text[]
        embedding_strings = [str(e) for e in query_embeddings]

        raw_results = self._db.rpc(
            "match_chunks_batch",
            params={
                "p_query_embeddings": embedding_strings,
                "p_source_type": source_type,
                "p_match_threshold": match_threshold,
                "p_match_count": match_count,
            },
        )

        # Group results by query_index
        grouped: dict[int, list[dict]] = {}
        for row in raw_results:
            idx = row["query_index"] - 1  # ORDINALITY is 1-based
            grouped.setdefault(idx, []).append({
                "id": row["id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "similarity": row["similarity"],
            })

        return grouped

    def compare_document_to_references(
        self,
        document_id: UUID,
        *,
        match_threshold: float = 0.5,
        match_count: int = 10,
    ) -> list[dict]:
        """Compare an uploaded document's chunks against all reference chunks.

        Uses batch RPC to avoid N+1 queries.  The HNSW index ensures
        no full-table scan — each query traverses the approximate
        nearest-neighbor graph in O(log n) time.

        Returns:
            List of match dicts sorted by similarity descending, with keys:
              upload_chunk_id, upload_chunk_index, upload_content,
              reference_chunk_id, reference_chunk_index, reference_content,
              similarity
        """
        # 1. Get all document chunks with embeddings
        doc_chunks = self._repo.list_by_source("upload", document_id)
        doc_chunks_with_emb = []
        embeddings: list[list[float]] = []

        for c in doc_chunks:
            emb = _parse_embedding(c.get("embedding"))
            if emb is not None:
                doc_chunks_with_emb.append(c)
                embeddings.append(emb)

        if not doc_chunks_with_emb:
            logger.warning("Document %s has no embedded chunks", document_id)
            return []

        # 2. Batch search — single RPC call for all doc chunk embeddings
        batch_results = self.match_chunks_batch(
            query_embeddings=embeddings,
            source_type="reference",
            match_threshold=match_threshold,
            match_count=match_count,
        )

        # 3. Assemble match list
        all_matches: list[dict] = []
        for idx, chunk in enumerate(doc_chunks_with_emb):
            for ref in batch_results.get(idx, []):
                all_matches.append({
                    "upload_chunk_id": chunk["id"],
                    "upload_chunk_index": chunk["chunk_index"],
                    "upload_content": chunk["content"],
                    "reference_chunk_id": ref["id"],
                    "reference_chunk_index": ref["chunk_index"],
                    "reference_content": ref["content"],
                    "similarity": ref["similarity"],
                })

        # Sort by similarity descending
        all_matches.sort(key=lambda m: m["similarity"], reverse=True)
        logger.info(
            "Document %s: found %d matches across %d chunks (batch)",
            document_id, len(all_matches), len(doc_chunks_with_emb),
        )
        return all_matches

    def semantic_search(
        self,
        query: str,
        *,
        source_type: str = "reference",
        match_threshold: float = 0.3,
        match_count: int = 10,
    ) -> list[dict]:
        """Search for chunks semantically similar to a free-text query.

        Encodes the query into an embedding vector, then searches the
        corpus using pgvector cosine similarity (HNSW index).

        Args:
            query: Free-text search query.
            source_type: "reference" or "upload".
            match_threshold: Minimum cosine similarity (0–1).
            match_count: Maximum number of results.

        Returns:
            List of chunk dicts with similarity scores.
        """
        from app.core.embedding import encode_query
        embedding = encode_query(query)

        results = self.match_chunks(
            query_embedding=embedding,
            source_type=source_type,
            match_threshold=match_threshold,
            match_count=match_count,
        )

        logger.info(
            "Semantic search '%s…' → %d results (threshold=%.2f)",
            query[:40], len(results), match_threshold,
        )
        return results

    # ── Paraphrase detection (semantic, lower threshold) ────────────

    def detect_paraphrases(
        self,
        document_id: UUID,
        *,
        min_similarity: float = 0.55,
        max_similarity: float = 0.90,
        match_count: int = 5,
    ) -> list[dict]:
        """Detect probable paraphrased segments using embedding similarity.

        Uses the same embeddings as semantic search but targets the
        "paraphrase zone" — similarity high enough to indicate rewriting
        (not just topical overlap) but below the near-exact-copy range
        that plagiarism detection handles.

        Threshold guide (cosine similarity):
          < 0.55  →  topically related, not a paraphrase
          0.55–0.90  →  probable paraphrase  ← this method
          > 0.90  →  near-exact copy (plagiarism detection handles this)

        Uses the batch RPC (single call for all doc chunks) and the
        HNSW index — no full-table scan.

        Args:
            document_id: UUID of the uploaded document.
            min_similarity: Lower bound cosine similarity (default 0.55).
            max_similarity: Upper bound — exclude near-exact copies (default 0.90).
            match_count: Max reference matches per doc chunk.

        Returns:
            List of paraphrase match dicts sorted by similarity descending:
              upload_chunk_id, upload_chunk_index, upload_content,
              reference_chunk_id, reference_chunk_index, reference_content,
              similarity
        """
        # 1. Get document chunks with embeddings
        doc_chunks = self._repo.list_by_source("upload", document_id)
        doc_chunks_with_emb = []
        embeddings: list[list[float]] = []

        for c in doc_chunks:
            emb = _parse_embedding(c.get("embedding"))
            if emb is not None:
                doc_chunks_with_emb.append(c)
                embeddings.append(emb)

        if not doc_chunks_with_emb:
            logger.warning("Document %s has no embedded chunks", document_id)
            return []

        # 2. Batch search with the lower threshold
        batch_results = self.match_chunks_batch(
            query_embeddings=embeddings,
            source_type="reference",
            match_threshold=min_similarity,
            match_count=match_count,
        )

        # 3. Filter to paraphrase zone: min_similarity <= sim < max_similarity
        paraphrases: list[dict] = []
        for idx, chunk in enumerate(doc_chunks_with_emb):
            for ref in batch_results.get(idx, []):
                sim = ref["similarity"]
                if sim < max_similarity:
                    paraphrases.append({
                        "upload_chunk_id": chunk["id"],
                        "upload_chunk_index": chunk["chunk_index"],
                        "upload_content": chunk["content"],
                        "reference_chunk_id": ref["id"],
                        "reference_chunk_index": ref["chunk_index"],
                        "reference_content": ref["content"],
                        "similarity": round(sim, 4),
                    })

        paraphrases.sort(key=lambda m: m["similarity"], reverse=True)
        logger.info(
            "Document %s: %d paraphrase matches (sim %.2f–%.2f)",
            document_id, len(paraphrases), min_similarity, max_similarity,
        )
        return paraphrases

    # ── Direct plagiarism detection (n-gram matching) ────────────────

    def detect_plagiarism(
        self,
        document_id: UUID,
        *,
        n: int = 7,
        min_jaccard: float = 0.1,
        min_containment: float = 0.2,
        max_matches_per_chunk: int = 5,
    ) -> list[dict]:
        """Detect direct plagiarism using n-gram hash matching.

        Compares each document chunk against all reference chunks using
        overlapping word n-grams.  Catches exact/near-exact copying that
        semantic similarity may miss.

        Args:
            document_id: UUID of the uploaded document.
            n: N-gram size in words (5–10 recommended).
            min_jaccard: Minimum Jaccard similarity to report.
            min_containment: Minimum containment score to report.
            max_matches_per_chunk: Cap matches per doc chunk.

        Returns:
            List of match dicts with keys:
              upload_chunk_id, upload_chunk_index, upload_content,
              reference_chunk_id, reference_chunk_index, reference_content,
              jaccard_score, containment_score, matched_ngrams
        """
        from app.core.plagiarism import detect_plagiarism as _detect

        doc_chunks = self._repo.list_by_source("upload", document_id)
        ref_chunks = self._repo.list_by_source("reference", document_id)

        # If no reference chunks for this specific document, get all references
        if not ref_chunks:
            ref_chunks = self._db.select("chunks", filters={"source_type": "eq.reference"})

        if not doc_chunks or not ref_chunks:
            logger.warning(
                "Plagiarism detection skipped: %d doc chunks, %d ref chunks",
                len(doc_chunks), len(ref_chunks),
            )
            return []

        results = _detect(
            doc_chunks,
            ref_chunks,
            n=n,
            min_jaccard=min_jaccard,
            min_containment=min_containment,
            max_matches_per_chunk=max_matches_per_chunk,
        )

        # Convert dataclasses to dicts for API response / DB storage
        return [
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
            for m in results
        ]

    def delete_by_document(self, document_id: UUID) -> None:
        self._repo.delete_by_source("upload", document_id)
