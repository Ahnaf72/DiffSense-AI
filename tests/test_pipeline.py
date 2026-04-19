"""Tests for the modular document processing pipeline."""

from pathlib import Path
from uuid import uuid4

from app.core.pipeline import (
    load_document,
    extract_content,
    chunk_document_text,
    generate_text_embeddings,
    compute_detection_score,
    pipeline_step,
)


class TestPipelineStepDecorator:
    def test_decorator_logs_success(self):
        @pipeline_step("test_step")
        def dummy_func():
            return {"result": "ok"}

        result = dummy_func()
        assert result == {"result": "ok"}

    def test_decorator_logs_failure(self):
        @pipeline_step("failing_step")
        def failing_func():
            raise ValueError("Test error")

        try:
            failing_func()
            assert False, "Should have raised"
        except ValueError:
            pass  # Expected


class TestLoadDocument:
    def test_load_existing_file(self):
        from app.core.config import settings
        upload_dir = Path(settings.upload_dir)
        upload_dir.mkdir(exist_ok=True)
        test_file = upload_dir / "test_pipeline.pdf"
        test_file.write_bytes(b"%PDF-1.4")
        try:
            result = load_document(uuid4(), test_file)
            assert result["exists"] is True
            assert result["file_size"] == 8
        finally:
            test_file.unlink(missing_ok=True)

    def test_load_nonexistent_file(self):
        try:
            load_document(uuid4(), Path("/nonexistent/file.pdf"))
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass  # Expected


class TestChunkDocumentText:
    def test_chunk_empty_text(self):
        result = chunk_document_text("")
        assert result["chunk_count"] == 0
        assert result["chunks"] == []

    def test_chunk_short_text(self):
        result = chunk_document_text("This is a longer sentence with enough words to pass the minimum token threshold for chunking.")
        assert result["chunk_count"] >= 1

    def test_chunk_long_text(self):
        text = " ".join(f"Word{i}" for i in range(100))
        result = chunk_document_text(text, max_tokens=20)
        assert result["chunk_count"] > 1
        for chunk in result["chunks"]:
            assert chunk["chunk_index"] >= 0
            assert chunk["content"]
            assert chunk["token_count"] > 0


class TestGenerateTextEmbeddings:
    def test_empty_chunks(self):
        result = generate_text_embeddings([])
        assert result["embeddings"] == []
        assert result["dimension"] == 0

    def test_single_chunk(self):
        chunks = [{"content": "Hello world"}]
        result = generate_text_embeddings(chunks, batch_size=1)
        assert len(result["embeddings"]) == 1
        assert result["dimension"] == 384

    def test_batch_chunks(self):
        chunks = [{"content": f"Text {i}"} for i in range(10)]
        result = generate_text_embeddings(chunks, batch_size=5)
        assert len(result["embeddings"]) == 10
        assert result["dimension"] == 384


class TestComputeDetectionScore:
    def test_all_empty(self):
        result = compute_detection_score([], [], [])
        assert result["final_score"] == 0.0
        assert result["breakdown"]["plagiarism"]["score"] == 0.0
        assert result["breakdown"]["paraphrase"]["score"] == 0.0
        assert result["breakdown"]["semantic"]["score"] == 0.0

    def test_plagiarism_only(self):
        matches = [{"containment_score": 0.8}, {"containment_score": 0.7}]
        result = compute_detection_score(matches, [], [])
        assert result["final_score"] > 0
        assert result["breakdown"]["plagiarism"]["score"] > 0
        assert result["breakdown"]["paraphrase"]["score"] == 0.0
        assert result["breakdown"]["semantic"]["score"] == 0.0

    def test_all_categories(self):
        plagiarism = [{"containment_score": 0.8}]
        paraphrase = [{"similarity": 0.6}]
        semantic = [{"similarity": 0.4}]
        result = compute_detection_score(plagiarism, paraphrase, semantic)
        assert result["final_score"] > 0
        assert result["breakdown"]["plagiarism"]["score"] > 0
        assert result["breakdown"]["paraphrase"]["score"] > 0
        assert result["breakdown"]["semantic"]["score"] > 0

    def test_score_breakdown_structure(self):
        matches = [{"containment_score": 0.8}]
        result = compute_detection_score(matches, [], [])
        assert "final_score" in result
        assert "breakdown" in result
        assert "plagiarism" in result["breakdown"]
        assert "paraphrase" in result["breakdown"]
        assert "semantic" in result["breakdown"]
