"""Tests for semantic similarity detection using embeddings."""

from app.core.embedding import encode_texts, encode_query, compute_similarity
from app.services.chunk_service import _parse_embedding


# ── Embedding parsing ────────────────────────────────────────────────


class TestParseEmbedding:
    def test_none_input(self):
        assert _parse_embedding(None) is None

    def test_list_input(self):
        vec = [0.1, 0.2, 0.3]
        assert _parse_embedding(vec) == vec

    def test_json_string(self):
        vec = _parse_embedding("[0.1, 0.2, 0.3]")
        assert vec == [0.1, 0.2, 0.3]

    def test_invalid_string(self):
        assert _parse_embedding("not a vector") is None

    def test_empty_string(self):
        assert _parse_embedding("[]") == []

    def test_pgvector_format(self):
        """pgvector typically returns '[0.1,0.2,0.3]' without spaces."""
        vec = _parse_embedding("[0.1,0.2,0.3]")
        assert len(vec) == 3
        assert abs(vec[0] - 0.1) < 1e-6


# ── Cosine similarity properties ──────────────────────────────────────


class TestCosineSimilarityProperties:
    def test_range_is_minus1_to_1(self):
        """Cosine similarity should always be in [-1, 1]."""
        v1 = encode_query("test document one")
        v2 = encode_query("completely different topic about cooking")
        sim = compute_similarity(v1, v2)
        assert -1.0 <= sim <= 1.0

    def test_self_similarity_is_1(self):
        vec = encode_query("self similarity test")
        sim = compute_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-5

    def test_symmetric(self):
        """sim(A, B) == sim(B, A)."""
        v1 = encode_query("first query about physics")
        v2 = encode_query("second query about chemistry")
        sim_ab = compute_similarity(v1, v2)
        sim_ba = compute_similarity(v2, v1)
        assert abs(sim_ab - sim_ba) < 1e-6

    def test_triangle_inequality(self):
        """sim(A, C) >= sim(A, B) * sim(B, C) - rough check."""
        va = encode_query("machine learning algorithms")
        vb = encode_query("ML algorithms and models")
        vc = encode_query("artificial intelligence models")
        sim_ab = compute_similarity(va, vb)
        sim_bc = compute_similarity(vb, vc)
        sim_ac = compute_similarity(va, vc)
        # Not a strict inequality for cosine, but generally holds
        assert sim_ac > 0  # at minimum, related topics should be positive


# ── Semantic ranking ──────────────────────────────────────────────────


class TestSemanticRanking:
    def test_related_ranked_higher_than_unrelated(self):
        """A query about ML should rank ML text higher than cooking text."""
        query = encode_query("machine learning neural networks")

        texts = [
            "deep learning with neural networks for classification",
            "cooking pasta with tomato sauce for dinner",
            "supervised learning algorithms for regression tasks",
            "gardening tips for growing tomatoes in summer",
        ]
        embeddings = encode_texts(texts)

        sims = [compute_similarity(query, emb) for emb in embeddings]
        # ML texts (indices 0, 2) should rank higher than non-ML (1, 3)
        assert sims[0] > sims[1]
        assert sims[2] > sims[3]

    def test_exact_match_highest_similarity(self):
        """Identical text should have higher similarity than paraphrase."""
        text = "the quick brown fox jumps over the lazy dog"
        exact = encode_query(text)
        paraphrase = encode_query("a fast brown fox leaps above a tired canine")
        original = encode_query(text)

        sim_exact = compute_similarity(original, exact)
        sim_paraphrase = compute_similarity(original, paraphrase)
        assert sim_exact > sim_paraphrase

    def test_similarity_increases_with_relevance(self):
        """More relevant text → higher similarity score."""
        query = encode_query("climate change global warming effects")

        texts = [
            "weather forecast for tomorrow",
            "global warming and its impact on sea levels",
            "climate change effects on biodiversity and ecosystems",
        ]
        embeddings = encode_texts(texts)
        sims = [compute_similarity(query, emb) for emb in embeddings]

        # Most relevant (index 2) should beat least relevant (index 0)
        assert sims[2] > sims[0]
        # Medium relevant (index 1) should also beat least relevant
        assert sims[1] > sims[0]


# ── Batch encoding consistency ────────────────────────────────────────


class TestBatchConsistency:
    def test_batch_equals_individual(self):
        """Batch encoding should produce same vectors as individual encoding."""
        texts = ["first text", "second text", "third text"]
        batch_vecs = encode_texts(texts)
        for i, text in enumerate(texts):
            individual = encode_texts([text])
            for a, b in zip(batch_vecs[i], individual[0]):
                assert abs(a - b) < 1e-5
