"""Tests for the text chunking module."""

from app.core.chunker import TextChunk, chunk_text, clean_text


class TestCleanText:
    def test_removes_control_chars(self):
        assert clean_text("hello\x00world\x01") == "helloworld"

    def test_collapses_whitespace(self):
        assert clean_text("hello   world\t\ttest") == "hello world test"

    def test_fixes_hyphenation(self):
        assert clean_text("com-\nputer") == "computer"

    def test_collapses_blank_lines(self):
        assert clean_text("a\n\n\n\nb") == "a\n\nb"

    def test_strips_leading_trailing(self):
        assert clean_text("  hello  ") == "hello"

    def test_empty_input(self):
        assert clean_text("") == ""
        assert clean_text("   ") == ""


class TestChunkText:
    def test_empty_input(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_single_paragraph(self):
        result = chunk_text("Hello world.", strategy="paragraph", min_chunk_tokens=1)
        assert len(result) == 1
        assert result[0].content == "Hello world."
        assert result[0].chunk_index == 0

    def test_multiple_paragraphs(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = chunk_text(text, strategy="paragraph", max_tokens=4, min_chunk_tokens=1)
        assert len(result) == 3
        assert result[0].chunk_index == 0
        assert result[2].chunk_index == 2

    def test_sentence_strategy(self):
        text = "First sentence. Second sentence. Third sentence."
        result = chunk_text(text, strategy="sentence", max_tokens=4, min_chunk_tokens=1)
        assert len(result) >= 2

    def test_max_tokens_respected(self):
        long_text = " ".join(f"Word{i}" for i in range(200))
        result = chunk_text(long_text, strategy="sentence", max_tokens=20)
        for chunk in result:
            assert chunk.token_count <= 25  # slight buffer for estimation

    def test_overlap_present(self):
        text = "First sentence here. Second sentence here. Third sentence here. Fourth sentence here."
        result_no_overlap = chunk_text(text, strategy="sentence", max_tokens=10, overlap_tokens=0)
        result_with_overlap = chunk_text(text, strategy="sentence", max_tokens=10, overlap_tokens=5)
        # Overlap should produce more total content (some text repeated)
        total_no = sum(c.char_count for c in result_no_overlap)
        total_with = sum(c.char_count for c in result_with_overlap)
        assert total_with >= total_no

    def test_min_chunk_tokens_filter(self):
        text = "Short. This is a longer sentence with more content in it."
        result = chunk_text(text, strategy="sentence", max_tokens=256, min_chunk_tokens=5)
        for chunk in result:
            assert chunk.token_count >= 5

    def test_chunk_index_sequential(self):
        text = "\n\n".join(f"Paragraph {i} with enough text to pass the minimum token threshold." for i in range(10))
        result = chunk_text(text, strategy="paragraph")
        for i, chunk in enumerate(result):
            assert chunk.chunk_index == i

    def test_returns_textchunk_instances(self):
        result = chunk_text("Hello world.", strategy="paragraph")
        for chunk in result:
            assert isinstance(chunk, TextChunk)
            assert isinstance(chunk.chunk_index, int)
            assert isinstance(chunk.content, str)
            assert isinstance(chunk.token_count, int)
            assert isinstance(chunk.char_count, int)
