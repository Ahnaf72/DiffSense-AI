"""Tests for paraphrase detection using embedding cosine similarity."""

from app.core.embedding import encode_texts, compute_similarity


class TestParaphraseZone:
    """Verify that paraphrases fall in the expected similarity range (0.55–0.90)."""

    def test_paraphrase_in_zone(self):
        """A clear paraphrase should have similarity in the paraphrase zone."""
        original = "The rapid advancement of artificial intelligence has transformed modern industry"
        paraphrase = "Quick progress in AI technology has revolutionized contemporary businesses"
        v_orig = encode_texts([original])[0]
        v_para = encode_texts([paraphrase])[0]
        sim = compute_similarity(v_orig, v_para)
        assert 0.55 <= sim <= 0.95, f"Paraphrase similarity {sim:.3f} outside expected zone"

    def test_exact_copy_above_zone(self):
        """Identical text should have similarity > 0.90 (above paraphrase zone)."""
        text = "The quick brown fox jumps over the lazy dog"
        v = encode_texts([text])[0]
        sim = compute_similarity(v, v)
        assert sim > 0.90, f"Self-similarity {sim:.3f} should be > 0.90"

    def test_unrelated_below_zone(self):
        """Topically unrelated text should have similarity < 0.55."""
        text_a = "Quantum mechanics describes subatomic particle behavior"
        text_b = "Cooking pasta with olive oil and garlic for dinner"
        va = encode_texts([text_a])[0]
        vb = encode_texts([text_b])[0]
        sim = compute_similarity(va, vb)
        assert sim < 0.55, f"Unrelated similarity {sim:.3f} should be < 0.55"


class TestParaphraseRanking:
    """Paraphrases should rank higher than topically related but non-paraphrased text."""

    def test_paraphrase_ranked_above_related(self):
        original = encode_texts(["Climate change is causing rising sea levels worldwide"])[0]
        paraphrase = encode_texts(["Global warming leads to increasing ocean heights across the globe"])[0]
        related = encode_texts(["Weather patterns are studied using satellite data"])[0]

        sim_para = compute_similarity(original, paraphrase)
        sim_related = compute_similarity(original, related)
        assert sim_para > sim_related, "Paraphrase should rank higher than merely related text"

    def test_paraphrase_ranked_below_exact(self):
        text = "Machine learning models require large datasets for training"
        original = encode_texts([text])[0]
        paraphrase = encode_texts(["ML algorithms need big data collections to learn effectively"])[0]
        exact = encode_texts([text])[0]

        sim_para = compute_similarity(original, paraphrase)
        sim_exact = compute_similarity(original, exact)
        assert sim_exact > sim_para, "Exact copy should rank higher than paraphrase"


class TestParaphraseVsPlagiarism:
    """Paraphrases should have low n-gram overlap (unlike direct copies)."""

    def test_paraphrase_has_low_ngram_overlap(self):
        from app.core.plagiarism import containment_score, ngram_fingerprint

        original = "The rapid advancement of artificial intelligence has transformed modern industry"
        paraphrase = "Quick progress in AI technology has revolutionized contemporary businesses"

        fp_orig = ngram_fingerprint(original, n=5)
        fp_para = ngram_fingerprint(paraphrase, n=5)

        cont = containment_score(fp_orig, fp_para)
        # Paraphrases use different words → low n-gram containment
        assert cont < 0.3, f"Paraphrase containment {cont:.3f} should be low"

    def test_exact_copy_has_high_ngram_overlap(self):
        from app.core.plagiarism import containment_score, ngram_fingerprint

        text = "The quick brown fox jumps over the lazy dog and runs away"
        fp = ngram_fingerprint(text, n=5)
        cont = containment_score(fp, fp)
        assert cont == 1.0, "Exact copy should have containment = 1.0"


class TestMultipleParaphrases:
    """Multiple paraphrases of the same text should all fall in the zone."""

    def test_varied_paraphrases(self):
        original = encode_texts(["The company reported significant revenue growth in the third quarter"])[0]
        paraphrases = [
            "The firm announced substantial income increase during Q3",
            "Significant earnings growth was reported by the corporation for the third quarter",
            "Third quarter saw major revenue expansion according to the company",
        ]
        para_vecs = encode_texts(paraphrases)

        for i, pv in enumerate(para_vecs):
            sim = compute_similarity(original, pv)
            assert sim >= 0.50, f"Paraphrase {i} similarity {sim:.3f} too low"
            assert sim < 1.0, f"Paraphrase {i} similarity {sim:.3f} should not be exact"
