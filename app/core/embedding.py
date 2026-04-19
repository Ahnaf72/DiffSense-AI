"""Thread-safe singleton loader for the sentence-transformers embedding model.

Usage:
    from app.core.embedding import encode_texts, encode_query

    vectors = encode_texts(["hello world", "second text"])
    query_vec = encode_query("search terms")
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np

from app.core.config import settings

logger = logging.getLogger(__name__)

_model: Any | None = None
_lock = threading.Lock()

# Default batch size for encoding — balances throughput vs memory
_DEFAULT_BATCH_SIZE = 64


def get_embedding_model() -> Any:
    """Return the singleton SentenceTransformer model.

    Loads on first call, then returns the cached instance.
    Thread-safe via a module-level lock.
    """
    global _model
    if _model is not None:
        return _model

    with _lock:
        # Double-checked locking
        if _model is not None:
            return _model

        from sentence_transformers import SentenceTransformer

        model_name = settings.embedding_model_name
        device = settings.embedding_device

        logger.info(
            "Loading embedding model '%s' on device '%s' …",
            model_name,
            device,
        )
        _model = SentenceTransformer(model_name, device=device)
        logger.info(
            "Embedding model loaded — dim=%d",
            _model.get_sentence_embedding_dimension(),
        )
        return _model


def unload_embedding_model() -> None:
    """Explicitly unload the model to free GPU/CPU memory."""
    global _model
    with _lock:
        if _model is not None:
            logger.info("Unloading embedding model")
            _model = None


def get_embedding_dimension() -> int:
    """Return the embedding dimension without loading the full model if already cached."""
    model = get_embedding_model()
    return model.get_sentence_embedding_dimension()


# ── High-level encoding helpers ──────────────────────────────────────


def encode_texts(
    texts: list[str],
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    show_progress_bar: bool = False,
) -> list[list[float]]:
    """Encode a list of texts into embedding vectors using batched inference.

    Args:
        texts: List of strings to encode.
        batch_size: Number of texts per forward pass. Lower values use
            less memory; higher values are faster on GPU.
        show_progress_bar: Whether to show a tqdm bar.

    Returns:
        List of float vectors, one per input text.
    """
    if not texts:
        return []

    model = get_embedding_model()
    all_vectors: list[list[float]] = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        logger.debug("Encoding batch %d-%d / %d", start, start + len(batch), len(texts))
        embeddings = model.encode(batch, show_progress_bar=False, convert_to_numpy=True)
        all_vectors.extend(embeddings.tolist())

    if show_progress_bar:
        logger.info("Encoded %d texts in %d batches", len(texts), -(-len(texts) // batch_size))

    return all_vectors


def encode_query(text: str) -> list[float]:
    """Encode a single query string into an embedding vector.

    Convenience wrapper around :func:`encode_texts` for single queries.
    """
    return encode_texts([text])[0]


def compute_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors.

    Returns a value in [-1, 1] where 1 = identical direction.
    """
    a = np.asarray(vec_a, dtype=np.float32)
    b = np.asarray(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
