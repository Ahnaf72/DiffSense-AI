"""Tests for the embedding model loader."""

from app.core.embedding import get_embedding_model, get_embedding_dimension, unload_embedding_model


class TestEmbeddingModel:
    def test_load_model(self):
        model = get_embedding_model()
        assert model is not None

    def test_singleton(self):
        m1 = get_embedding_model()
        m2 = get_embedding_model()
        assert m1 is m2

    def test_encode(self):
        model = get_embedding_model()
        vectors = model.encode(["hello world"], show_progress_bar=False)
        assert vectors.shape[0] == 1
        assert vectors.shape[1] == 384

    def test_dimension(self):
        dim = get_embedding_dimension()
        assert dim == 384

    def test_unload(self):
        unload_embedding_model()
        # After unload, next call should reload
        model = get_embedding_model()
        assert model is not None
