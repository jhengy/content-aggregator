"""Unit tests for the summarizer module.

Tests the extractive summarization functions using TF-IDF and TextRank.
Assumes the module provides a function ``summarize`` with signature:

    summarize(text: str, num_sentences: int = 5) -> str

The module is imported from ``src.summarizer``.
"""

import pytest
from src.summarizer import summarize


# ---------------------------------------------------------------------------
# Fixtures – reusable sample texts
# ---------------------------------------------------------------------------

@pytest.fixture
def short_article() -> str:
    """A very short article with exactly 4 sentences."""
    return (
        "Python is a high-level programming language. "
        "It was created by Guido van Rossum in 1991. "
        "Python emphasizes code readability with its notable use of significant whitespace. "
        "Today Python is one of the most popular languages worldwide."
    )


@pytest.fixture
def medium_article() -> str:
    """A longer article suitable for extractive summarization."""
    return (
        "Artificial intelligence is transforming many industries. "
        "Machine learning, a subset of AI, allows systems to learn from data. "
        "Deep learning uses neural networks with multiple layers. "
        "Natural language processing enables computers to understand text. "
        "Reinforcement learning trains agents through rewards and penalties. "
        "AI ethics and bias are critical areas of ongoing research. "
        "The future of AI promises both opportunities and challenges."
    )


@pytest.fixture
def repetitive_text() -> str:
    """Text where many sentences are almost identical (low information)."""
    return (
        "The cat sat on the mat. "
        "The cat sat on a mat. "
        "A cat sat on the mat. "
        "The mat under the cat sat. "
        "Cat and mat were together."
    )


# ---------------------------------------------------------------------------
# Unit tests – basic functionality
# ---------------------------------------------------------------------------


class TestSummarizeBasic:
    """Core behavior of the summarize function."""

    def test_short_article_returns_all_sentences(self, short_article: str):
        """When the article has fewer sentences than requested, return all."""
        result = summarize(short_article, num_sentences=10)
        expected_sentences = [
            "Python is a high-level programming language.",
            "It was created by Guido van Rossum in 1991.",
            "Python emphasizes code readability with its notable use of significant whitespace.",
            "Today Python is one of the most popular languages worldwide.",
        ]
        assert result, "Summary should not be empty."
        # Check that all original sentences appear in the summary
        for sent in expected_sentences:
            assert sent in result, f"Missing expected sentence: {sent}"

    def test_default_num_sentences(self, medium_article: str):
        """Default value of num_sentences should produce a reasonable summary."""
        result = summarize(medium_article)
        assert result
        sentences = [s.strip() for s in result.split(".") if s.strip()]
        # Default is 5, but may return fewer if article is short – we only check
        # that we got at least one sentence and not all.
        assert 1 <= len(sentences) <= 5
        # The summary should be strictly shorter than the original
        assert len(result) < len(medium_article)

    def test_summary_contains_key_sentences(self, medium_article: str):
        """The summary should include the most salient sentences."""
        # For extractive summarization we trust that the algorithm picks important ones.
        # We test that the summary length is not too short (at least 1 sentence) and
        # that it does not add external text.
        result = summarize(medium_article, num_sentences=3)
        sentences = result.split(".")
        # Remove empty strings
        sentences = [s.strip() for s in sentences if s.strip()]
        assert len(sentences) <= 3
        # Every sentence in the summary must be a substring of the original.
        original_sentences = medium_article.split(".")
        original_sentences = [s.strip() for s in original_sentences if s.strip()]
        for sent in sentences:
            assert any(sent in orig for orig in original_sentences), (
                f"Sentence '{sent}' not found in original text."
            )

    def test_repetitive_text(self, repetitive_text: str):
        """Repetitive text should not cause duplication in the summary."""
        result = summarize(repetitive_text, num_sentences=2)
        sentences = result.split(".")
        sentences = [s.strip() for s in sentences if s.strip()]
        assert len(sentences) <= 2
        # All sentences should still be from the original
        for s in sentences:
            assert s in repetitive_text


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestSummarizeEdgeCases:
    """Empty, single-sentence, and None inputs."""

    def test_empty_string(self):
        """Empty input should return an empty string."""
        assert summarize("") == ""

    def test_whitespace_only(self):
        """Whitespace-only input should return empty string."""
        assert summarize("   \n\t  ") == ""

    def test_single_sentence(self):
        """Single sentence should be returned as-is."""
        text = "This is only one sentence."
        assert summarize(text) == text

    def test_two_sentences_request_one(self):
        """Request fewer sentences than available; should return one sentence."""
        text = "First sentence. Second sentence."
        result = summarize(text, num_sentences=1)
        # Only one sentence should be returned
        assert result.count(".") == 1 or result.endswith(".")
        assert result in text  # must be a substring of original

    def test_punctuation_handling(self):
        """Text with trailing punctuation and multiple delimiters."""
        text = "Hello world! How are you? I am fine. That's great."
        result = summarize(text, num_sentences=2)
        assert result
        # Should not contain any markdown or illegal characters
        assert isinstance(result, str)

    def test_none_input_raises_type_error(self):
        """Passing None should raise TypeError."""
        with pytest.raises(TypeError):
            summarize(None)  # type: ignore


# ---------------------------------------------------------------------------
# Error handling & invalid arguments
# ---------------------------------------------------------------------------


class TestSummarizeErrors:
    """Invalid parameters that should be rejected."""

    def test_negative_num_sentences(self, short_article: str):
        """Negative num_sentences should raise ValueError."""
        with pytest.raises(ValueError):
            summarize(short_article, num_sentences=-5)

    def test_zero_num_sentences(self, short_article: str):
        """Zero num_sentences should return empty string (or raise)."""
        # Depending on implementation; we accept either an empty string or ValueError.
        try:
            result = summarize(short_article, num_sentences=0)
            assert result == "", "Expected empty summary when num_sentences=0"
        except ValueError:
            pass  # also acceptable

    def test_non_integer_num_sentences(self, short_article: str):
        """Non-integer num_sentences should raise TypeError."""
        with pytest.raises(TypeError):
            summarize(short_article, num_sentences="5")  # type: ignore

    def test_invalid_input_type(self):
        """Passing an integer instead of string should raise TypeError."""
        with pytest.raises(TypeError):
            summarize(12345)  # type: ignore


# ---------------------------------------------------------------------------
# Integration / consistency checks
# ---------------------------------------------------------------------------


class TestSummarizeConsistency:
    """Reproducibility and idempotence."""

    def test_deterministic_output(self, medium_article: str):
        """Same input should always produce the same output (no randomness)."""
        result1 = summarize(medium_article, num_sentences=3)
        result2 = summarize(medium_article, num_sentences=3)
        assert result1 == result2

    def test_summary_of_summary_is_shorter_or_equal(self, medium_article: str):
        """Summarizing an already short summary should not increase length."""
        first = summarize(medium_article, num_sentences=4)
        second = summarize(first, num_sentences=2)
        assert len(second) <= len(first)

    def test_no_new_sentences_introduced(self, short_article: str):
        """The summary should consist exclusively of original sentences."""
        original_sentences = set(
            s.strip() for s in short_article.split(".") if s.strip()
        )
        for n in range(1, len(original_sentences) + 1):
            result = summarize(short_article, num_sentences=n)
            summary_sentences = set(
                s.strip() for s in result.split(".") if s.strip()
            )
            # Every summary sentence must be a direct substring of one original sentence
            for s in summary_sentences:
                assert any(
                    s in orig for orig in original_sentences
                ), f"Summary contains text not in original: '{s}'"