"""Tests for direct plagiarism detection via n-gram matching."""

from app.core.plagiarism import (
    extract_ngrams,
    ngram_fingerprint,
    jaccard_similarity,
    containment_score,
    detect_plagiarism,
    PlagiarismMatch,
)


# ── N-gram extraction ────────────────────────────────────────────────


class TestExtractNgrams:
    def test_basic(self):
        ngrams = extract_ngrams("the quick brown fox jumps over the lazy dog", n=5)
        assert len(ngrams) == 5  # 9 words - 5 + 1
        assert ngrams[0] == "the quick brown fox jumps"
        assert ngrams[-1] == "jumps over the lazy dog"

    def test_short_text(self):
        """Text shorter than n produces no n-grams."""
        assert extract_ngrams("hello world", n=5) == []

    def test_exact_length(self):
        """Text with exactly n words produces one n-gram."""
        ngrams = extract_ngrams("one two three four five", n=5)
        assert len(ngrams) == 1
        assert ngrams[0] == "one two three four five"

    def test_punctuation_stripped(self):
        ngrams = extract_ngrams("Hello, world! This is a test sentence here.", n=5)
        assert ngrams[0] == "hello world this is a"

    def test_case_insensitive(self):
        ngrams = extract_ngrams("The Quick Brown Fox Jumps", n=5)
        assert ngrams[0] == "the quick brown fox jumps"

    def test_n7(self):
        text = " ".join(f"word{i}" for i in range(20))
        ngrams = extract_ngrams(text, n=7)
        assert len(ngrams) == 14  # 20 - 7 + 1
        for ng in ngrams:
            assert len(ng.split()) == 7


# ── Fingerprinting ────────────────────────────────────────────────────


class TestNgramFingerprint:
    def test_produces_set_of_ints(self):
        fp = ngram_fingerprint("the quick brown fox jumps over the lazy dog", n=5)
        assert isinstance(fp, set)
        assert all(isinstance(h, int) for h in fp)

    def test_deterministic(self):
        text = "the quick brown fox jumps over the lazy dog"
        fp1 = ngram_fingerprint(text, n=5)
        fp2 = ngram_fingerprint(text, n=5)
        assert fp1 == fp2

    def test_empty_text(self):
        assert ngram_fingerprint("", n=5) == set()

    def test_short_text(self):
        assert ngram_fingerprint("hello", n=5) == set()

    def test_identical_texts_same_fingerprint(self):
        fp1 = ngram_fingerprint("the quick brown fox jumps", n=5)
        fp2 = ngram_fingerprint("the quick brown fox jumps", n=5)
        assert fp1 == fp2

    def test_different_texts_different_fingerprint(self):
        fp1 = ngram_fingerprint("the quick brown fox jumps", n=5)
        fp2 = ngram_fingerprint("a completely different sentence here", n=5)
        assert fp1 != fp2


# ── Jaccard similarity ────────────────────────────────────────────────


class TestJaccardSimilarity:
    def test_identical_sets(self):
        fp = {1, 2, 3}
        assert jaccard_similarity(fp, fp) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_similarity({1, 2, 3}, {4, 5, 6}) == 0.0

    def test_partial_overlap(self):
        sim = jaccard_similarity({1, 2, 3, 4}, {3, 4, 5, 6})
        # intersection = {3,4} = 2, union = {1,2,3,4,5,6} = 6
        assert abs(sim - 2 / 6) < 1e-6

    def test_empty_sets(self):
        assert jaccard_similarity(set(), {1, 2}) == 0.0
        assert jaccard_similarity({1, 2}, set()) == 0.0


# ── Containment score ─────────────────────────────────────────────────


class TestContainmentScore:
    def test_full_containment(self):
        assert containment_score({1, 2}, {1, 2, 3, 4}) == 1.0

    def test_partial_containment(self):
        score = containment_score({1, 2, 3}, {3, 4, 5})
        # intersection = {3} = 1, subset size = 3
        assert abs(score - 1 / 3) < 1e-6

    def test_no_containment(self):
        assert containment_score({1, 2}, {3, 4}) == 0.0

    def test_empty(self):
        assert containment_score(set(), {1, 2}) == 0.0


# ── Full detection ────────────────────────────────────────────────────


class TestDetectPlagiarism:
    def _make_chunk(self, id: str, index: int, content: str) -> dict:
        return {"id": id, "chunk_index": index, "content": content}

    def test_exact_copy_detected(self):
        doc = [self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog")]
        ref = [self._make_chunk("r1", 0, "The quick brown fox jumps over the lazy dog")]
        matches = detect_plagiarism(doc, ref, n=5, min_containment=0.5)
        assert len(matches) >= 1
        assert matches[0].containment_score == 1.0
        assert matches[0].jaccard_score == 1.0

    def test_partial_copy_detected(self):
        doc = [self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog and runs away")]
        ref = [self._make_chunk("r1", 0, "The quick brown fox jumps over the lazy dog in the park")]
        matches = detect_plagiarism(doc, ref, n=5, min_containment=0.2, min_jaccard=0.05)
        assert len(matches) >= 1
        assert matches[0].containment_score > 0.0

    def test_no_copy_not_detected(self):
        doc = [self._make_chunk("d1", 0, "Quantum mechanics describes the behavior of subatomic particles")]
        ref = [self._make_chunk("r1", 0, "Cooking recipes for dinner include pasta and salad")]
        matches = detect_plagiarism(doc, ref, n=5, min_containment=0.2)
        assert len(matches) == 0

    def test_matched_ngrams_populated(self):
        doc = [self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog")]
        ref = [self._make_chunk("r1", 0, "The quick brown fox jumps over the lazy dog")]
        matches = detect_plagiarism(doc, ref, n=5, min_containment=0.5)
        assert len(matches) >= 1
        assert len(matches[0].matched_ngrams) > 0
        assert "the quick brown fox jumps" in matches[0].matched_ngrams

    def test_max_matches_per_chunk(self):
        doc = [self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog")]
        refs = [self._make_chunk(f"r{i}", i, "The quick brown fox jumps over the lazy dog") for i in range(10)]
        matches = detect_plagiarism(doc, refs, n=5, min_containment=0.5, max_matches_per_chunk=3)
        assert len(matches) <= 3

    def test_multiple_doc_chunks(self):
        docs = [
            self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog"),
            self._make_chunk("d2", 1, "A completely different sentence about cooking dinner"),
        ]
        refs = [self._make_chunk("r1", 0, "The quick brown fox jumps over the lazy dog")]
        matches = detect_plagiarism(docs, refs, n=5, min_containment=0.3)
        # Only d1 should match
        assert all(m.upload_chunk_id == "d1" for m in matches)

    def test_empty_inputs(self):
        assert detect_plagiarism([], [], n=5) == []
        doc = [self._make_chunk("d1", 0, "Some text here with enough words to form ngrams")]
        assert detect_plagiarism(doc, [], n=5) == []

    def test_returns_plagiarism_match_instances(self):
        doc = [self._make_chunk("d1", 0, "The quick brown fox jumps over the lazy dog")]
        ref = [self._make_chunk("r1", 0, "The quick brown fox jumps over the lazy dog")]
        matches = detect_plagiarism(doc, ref, n=5, min_containment=0.5)
        for m in matches:
            assert isinstance(m, PlagiarismMatch)
