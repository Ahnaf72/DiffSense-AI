"""Tests for the embedding pipeline — encode_texts, encode_query, compute_similarity."""

import math

from app.core.embedding import (
    encode_texts,
    encode_query,
    compute_similarity,
    get_embedding_dimension,
    unload_embedding_model,
)


class TestEncodeTexts:
    def test_single_text(self):
        vecs = encode_texts(["hello world"])
        assert len(vecs) == 1
        assert len(vecs[0]) == 384

    def test_multiple_texts(self):
        vecs = encode_texts(["first text", "second text", "third text"])
        assert len(vecs) == 3
        for v in vecs:
            assert len(v) == 384

    def test_batched_encoding(self):
        """Batch size smaller than input — should still produce correct count."""
        texts = [f"text number {i}" for i in range(10)]
        vecs = encode_texts(texts, batch_size=3)
        assert len(vecs) == 10
        for v in vecs:
            assert len(v) == 384

    def test_empty_input(self):
        assert encode_texts([]) == []

    def test_deterministic(self):
        """Same input → same output."""
        v1 = encode_texts(["deterministic test"])
        v2 = encode_texts(["deterministic test"])
        for a, b in zip(v1[0], v2[0]):
            assert abs(a - b) < 1e-6


class TestEncodeQuery:
    def test_returns_single_vector(self):
        vec = encode_query("search query")
        assert isinstance(vec, list)
        assert len(vec) == 384


class TestComputeSimilarity:
    def test_identical_vectors(self):
        vec = [1.0, 0.0, 0.0]
        sim = compute_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [-1.0, 0.0, 0.0]
        sim = compute_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0, 0.0]
        b = [0.0, 1.0, 0.0]
        sim = compute_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_zero_vector(self):
        sim = compute_similarity([0.0, 0.0], [1.0, 0.0])
        assert sim == 0.0

    def test_similar_texts_high_similarity(self):
        v1 = encode_query("machine learning algorithms")
        v2 = encode_query("ML algorithms")
        sim = compute_similarity(v1, v2)
        assert sim > 0.5, f"Expected high similarity, got {sim:.3f}"

    def test_dissimilar_texts_low_similarity(self):
        v1 = encode_query("quantum physics equations")
        v2 = encode_query("cooking recipes for dinner")
        sim = compute_similarity(v1, v2)
        assert sim < 0.5, f"Expected low similarity, got {sim:.3f}"


class TestEmbeddingDimension:
    def test_dimension(self):
        dim = get_embedding_dimension()
        assert dim == 384
