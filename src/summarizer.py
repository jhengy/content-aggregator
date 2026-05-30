"""
Extractive summarization using spaCy and TextRank.

This module implements a TextRank-based extractive summarizer
with spaCy for linguistic preprocessing. It produces a condensed
digest by selecting the most representative sentences.

Typical usage:
    text = "Your long document text here."
    summary = TextRankSummarizer().summarize(text, num_sentences=3)
"""

from __future__ import annotations

import itertools
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple, Union
from collections.abc import Iterator

import numpy as np
import numpy.typing as npt
import spacy
from spacy.errors import SpacyIOError
from spacy.language import Language
from spacy.tokens import Doc, Span

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------
class SummarizerError(Exception):
    """Base exception for summarizer-specific errors."""

class ModelLoadError(SummarizerError):
    """Raised when the spaCy model cannot be loaded."""

class TextPreprocessingError(SummarizerError):
    """Raised during text preprocessing failures."""

class EmptyTextError(SummarizerError):
    """Raised when the input text is empty or whitespace only."""

class InsufficientSentencesError(SummarizerError):
    """Raised when the text contains fewer sentences than requested."""

class InvalidParameterError(SummarizerError):
    """Raised when a parameter is invalid (type or value)."""

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "en_core_web_sm"
_DEFAULT_NUM_SENTENCES = 5
_DEFAULT_DAMPING_FACTOR = 0.85
_DEFAULT_MAX_ITERATIONS = 100
_DEFAULT_TOLERANCE = 1e-4
_DEFAULT_MIN_SENTENCE_LENGTH = 10
_DEFAULT_USE_FAST_SIMILARITY = True

_VALID_POS_TAGS = {"NOUN", "PROPN", "ADJ", "VERB", "ADV"}

# Maximum allowed text length to prevent memory issues (characters)
_MAX_TEXT_LENGTH = 1_000_000

# ---------------------------------------------------------------------------
# Data classes for internal use
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SentenceCandidate:
    """Internal representation of a sentence with its preprocessed tokens."""

    text: str
    tokens: list[str]
    index: int

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _validate_positive_int(value: object, name: str) -> int:
    """Validate that *value* is a positive integer.

    Args:
        value: The value to check.
        name: The parameter name for error messages.

    Returns:
        The validated integer.

    Raises:
        InvalidParameterError: If *value* is not a positive integer.
    """
    if not isinstance(value, int):
        raise InvalidParameterError(
            f"`{name}` must be an integer, got {type(value).__name__}."
        )
    if value < 1:
        raise InvalidParameterError(
            f"`{name}` must be positive, got {value}."
        )
    return value

def _validate_non_negative_int(value: object, name: str) -> int:
    """Validate that *value* is a non‑negative integer.

    Args:
        value: The value to check.
        name: The parameter name for error messages.

    Returns:
        The validated integer.

    Raises:
        InvalidParameterError: If *value* is not a non‑negative integer.
    """
    if not isinstance(value, int):
        raise InvalidParameterError(
            f"`{name}` must be an integer, got {type(value).__name__}."
        )
    if value < 0:
        raise InvalidParameterError(
            f"`{name}` must be non‑negative, got {value}."
        )
    return value

def _validate_float_range(
    value: object,
    name: str,
    low: float,
    high: float,
    include_low: bool = True,
    include_high: bool = False,
) -> float:
    """Validate a float within a range.

    Args:
        value: The value to validate.
        name: The parameter name.
        low: Lower bound.
        high: Upper bound.
        include_low: Whether *low* is inclusive.
        include_high: Whether *high* is inclusive.

    Returns:
        The validated float.

    Raises:
        InvalidParameterError: If *value* is not numeric or outside range.
    """
    if not isinstance(value, (int, float)):
        raise InvalidParameterError(
            f"`{name}` must be numeric, got {type(value).__name__}."
        )
    num = float(value)
    if include_low:
        if num < low:
            raise InvalidParameterError(
                f"`{name}` must be >= {low}, got {num}."
            )
    else:
        if num <= low:
            raise InvalidParameterError(
                f"`{name}` must be > {low}, got {num}."
            )
    if include_high:
        if num > high:
            raise InvalidParameterError(
                f"`{name}` must be <= {high}, got {num}."
            )
    else:
        if num >= high:
            raise InvalidParameterError(
                f"`{name}` must be < {high}, got {num}."
            )
    return num

def _validate_model(value: object) -> str:
    """Validate that the model name is a non-empty string.

    Args:
        value: The spaCy model name.

    Returns:
        The validated model name.

    Raises:
        InvalidParameterError: If *value* is not a non-empty string.
    """
    if not isinstance(value, str):
        raise InvalidParameterError(
            f"`model` must be a string, got {type(value).__name__}."
        )
    stripped = value.strip()
    if not stripped:
        raise InvalidParameterError("`model` must not be empty.")
    return stripped

def _validate_text(value: object) -> str:
    """Validate that the text is a non-empty, non-whitespace string.

    Performs a length check to avoid processing extremely large inputs.

    Args:
        value: The input text.

    Returns:
        The validated text (original, not stripped).

    Raises:
        EmptyTextError: If *value* is not a string or is empty/whitespace.
        TextPreprocessingError: If text exceeds maximum allowed length.
    """
    if not isinstance(value, str):
        raise EmptyTextError(
            f"Input text must be a string, got {type(value).__name__}."
        )
    if not value.strip():
        raise EmptyTextError("Input text is empty or contains only whitespace.")
    if len(value) > _MAX_TEXT_LENGTH:
        raise TextPreprocessingError(
            f"Input text exceeds maximum length of {_MAX_TEXT_LENGTH} characters."
        )
    return value

def _validate_bool(value: object, name: str) -> bool:
    """Validate that *value* is a bool.

    Args:
        value: The value to check.
        name: The parameter name.

    Returns:
        The validated bool.

    Raises:
        InvalidParameterError: If *value* is not a bool.
    """
    if not isinstance(value, bool):
        raise InvalidParameterError(
            f"`{name}` must be a bool, got {type(value).__name__}."
        )
    return value

# ---------------------------------------------------------------------------
# Main summarizer class
# ---------------------------------------------------------------------------
class TextRankSummarizer:
    """Extractive summarizer using the TextRank algorithm with spaCy.

    Attributes:
        model_name: Name of the installed spaCy model.
        num_sentences: Default number of sentences in the summary.
        damping_factor: PageRank damping factor (0 < d < 1).
        max_iterations: Maximum PageRank iterations before convergence.
        tolerance: Convergence threshold for PageRank.
        min_sentence_length: Minimum character length to keep a sentence.
        use_fast_similarity: If True, use an optimised vectorised similarity
            computation. Otherwise falls back to the per‑pair loop.

    The summarizer loads the spaCy model once and reuses it across calls.
    Thread‑safe as long as the spaCy model is not modified concurrently.
    """

    __slots__ = (
        "_model_name",
        "_num_sentences",
        "_damping_factor",
        "_max_iterations",
        "_tolerance",
        "_min_sentence_length",
        "_use_fast_similarity",
        "_nlp",
    )

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        num_sentences: int = _DEFAULT_NUM_SENTENCES,
        damping_factor: float = _DEFAULT_DAMPING_FACTOR,
        max_iterations: int = _DEFAULT_MAX_ITERATIONS,
        tolerance: float = _DEFAULT_TOLERANCE,
        min_sentence_length: int = _DEFAULT_MIN_SENTENCE_LENGTH,
        use_fast_similarity: bool = _DEFAULT_USE_FAST_SIMILARITY,
    ) -> None:
        """Initialize the summarizer with the given parameters.

        Args:
            model: Name of the spaCy model to load.
            num_sentences: Default number of sentences for summary.
            damping_factor: PageRank damping factor (0 < d < 1).
            max_iterations: Maximum PageRank iterations.
            tolerance: Convergence threshold for PageRank.
            min_sentence_length: Minimum character length for a sentence.
            use_fast_similarity: Use optimised similarity computation.

        Raises:
            InvalidParameterError: If any parameter is invalid.
            ModelLoadError: If the spaCy model cannot be loaded.
        """
        self._model_name = _validate_model(model)
        self._num_sentences = _validate_positive_int(num_sentences, "num_sentences")
        self._damping_factor = _validate_float_range(
            damping_factor, "damping_factor", 0.0, 1.0, include_low=False, include_high=False
        )
        self._max_iterations = _validate_positive_int(max_iterations, "max_iterations")
        self._tolerance = _validate_float_range(
            tolerance, "tolerance", 0.0, 1.0, include_low=False
        )
        self._min_sentence_length = _validate_non_negative_int(
            min_sentence_length, "min_sentence_length"
        )
        self._use_fast_similarity = _validate_bool(use_fast_similarity, "use_fast_similarity")
        self._nlp: Language = self._load_model()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------
    def _load_model(self) -> Language:
        """Load the spaCy language model.

        Returns:
            Loaded spaCy Language object.

        Raises:
            ModelLoadError: If loading fails (e.g., model not installed).
        """
        logger.info("Loading spaCy model '%s'...", self._model_name)
        try:
            nlp = spacy.load(self._model_name)
        except OSError as exc:
            error_msg = (
                f"Model '{self._model_name}' not found. "
                "Please install it using: python -m spacy download {model}"
            ).format(model=self._model_name)
            logger.error(error_msg)
            raise ModelLoadError(error_msg) from exc
        except SpacyIOError as exc:
            error_msg = f"Error loading spaCy model '{self._model_name}'."
            logger.error(error_msg)
            raise ModelLoadError(error_msg) from exc
        except Exception as exc:
            error_msg = f"Unexpected error loading model '{self._model_name}'."
            logger.exception(error_msg)
            raise ModelLoadError(error_msg) from exc
        logger.info("Successfully loaded model '%s'.", self._model_name)
        return nlp

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def summarize(
        self,
        text: str,
        num_sentences: Optional[int] = None,
    ) -> List[str]:
        """Generate an extractive summary of the input text.

        Args:
            text: The input document as a string.
            num_sentences: Number of sentences for the summary.
                If None, uses the default set in the constructor.

        Returns:
            A list of sentences forming the summary, in original order.

        Raises:
            EmptyTextError: If text is empty or only whitespace.
            InvalidParameterError: If num_sentences is invalid.
            InsufficientSentencesError: If text has fewer sentences than
                requested.
            TextPreprocessingError: If preprocessing fails.
        """
        # Validate inputs
        text = _validate_text(text)
        target_sentences = (
            _validate_positive_int(num_sentences, "num_sentences") if num_sentences is not None
            else self._num_sentences
        )

        # Preprocess
        try:
            candidates = self._extract_candidates(text)
        except EmptyTextError:
            raise
        except Exception as exc:
            logger.exception("Preprocessing failed for input text.")
            raise TextPreprocessingError("Failed to preprocess text.") from exc

        if len(candidates) < target_sentences:
            raise InsufficientSentencesError(
                f"Text has {len(candidates)} sentences, but {target_sentences} requested."
            )

        if len(candidates) == 0:
            raise InsufficientSentencesError("No viable sentences after preprocessing.")

        # Build similarity matrix and run PageRank
        similarity_matrix = self._build_similarity_matrix(candidates)
        scores = self._page_rank(similarity_matrix)

        # Select top-ranked sentences, preserving original order
        sentence_indices = np.argsort(scores)[::-1][:target_sentences]
        selected_indices = sorted(sentence_indices)

        # Build result preserving original order
        result = [candidates[i].text for i in selected_indices]

        logger.info(
            "Summary generated: %d sentences from %d candidates.",
            len(result),
            len(candidates),
        )
        return result

    # ------------------------------------------------------------------
    # Internal preprocessing
    # ------------------------------------------------------------------
    def _extract_candidates(self, text: str) -> List[SentenceCandidate]:
        """Extract sentence candidates from raw text.

        Uses spaCy's sentence segmentation and filters based on length
        and token content.

        Args:
            text: The input document.

        Returns:
            List of SentenceCandidate objects.

        Raises:
            TextPreprocessingError: If spaCy processing fails.
        """
        try:
            doc: Doc = self._nlp(text)
        except Exception as exc:
            logger.exception("spaCy processing failed.")
            raise TextPreprocessingError("Failed to process text with spaCy.") from exc

        candidates: List[SentenceCandidate] = []
        for sent in doc.sents:
            # Filter by length
            sentence_text = sent.text.strip()
            if len(sentence_text) < self._min_sentence_length:
                continue

            # Extract tokens with allowed POS tags
            tokens = [
                token.text.lower()
                for token in sent
                if not token.is_punct and not token.is_space and token.pos_ in _VALID_POS_TAGS
            ]

            if not tokens:
                continue

            candidates.append(
                SentenceCandidate(
                    text=sentence_text,
                    tokens=tokens,
                    index=len(candidates),
                )
            )

        if not candidates:
            logger.warning("No sentence candidates found after preprocessing.")

        return candidates

    # ------------------------------------------------------------------
    # Similarity matrix construction
    # ------------------------------------------------------------------
    def _build_similarity_matrix(
        self,
        candidates: List[SentenceCandidate],
    ) -> npt.NDArray[np.float64]:
        """Build the pairwise similarity matrix for the candidates.

        Uses token overlap (Jaccard similarity) as a fast approximation.

        Args:
            candidates: List of sentence candidates.

        Returns:
            A 2D numpy array of shape (n, n) with similarity values.
        """
        n = len(candidates)
        if n == 0:
            return np.zeros((0, 0), dtype=np.float64)

        if self._use_fast_similarity and n > 1:
            return self._fast_similarity_matrix(candidates)
        else:
            return self._pairwise_similarity_matrix(candidates)

    def _pairwise_similarity_matrix(
        self,
        candidates: List[SentenceCandidate],
    ) -> npt.NDArray[np.float64]:
        """Compute similarity matrix using pairwise Jaccard similarity.

        Args:
            candidates: List of sentence candidates.

        Returns:
            A 2D numpy array of shape (n, n) with similarity values.
        """
        n = len(candidates)
        matrix = np.eye(n, dtype=np.float64)

        for i, j in itertools.combinations(range(n), 2):
            similarity = self._jaccard_similarity(
                set(candidates[i].tokens), set(candidates[j].tokens)
            )
            matrix[i][j] = similarity
            matrix[j][i] = similarity

        return matrix

    def _fast_similarity_matrix(
        self,
        candidates: List[SentenceCandidate],
    ) -> npt.NDArray[np.float64]:
        """Compute similarity matrix using vectorised operations.

        Builds a token‑sentence matrix and computes Jaccard similarity
        in a vectorised manner.

        Args:
            candidates: List of sentence candidates.

        Returns:
            A 2D numpy array of shape (n, n) with similarity values.
        """
        n = len(candidates)
        # Build vocabulary
        vocab: Dict[str, int] = {}
        token_ids: List[Set[int]] = []
        for candidate in candidates:
            ids = set()
            for token in candidate.tokens:
                if token not in vocab:
                    vocab[token] = len(vocab)
                ids.add(vocab[token])
            token_ids.append(ids)

        # Create sparse representation as a list of sets, compute pairwise Jaccard
        matrix = np.eye(n, dtype=np.float64)
        for i in range(n):
            set_i = token_ids[i]
            len_i = len(set_i)
            for j in range(i + 1, n):
                set_j = token_ids[j]
                intersection = len(set_i & set_j)
                union = len_i + len(set_j) - intersection
                similarity = intersection / union if union > 0 else 0.0
                matrix[i][j] = similarity
                matrix[j][i] = similarity

        return matrix

    @staticmethod
    def _jaccard_similarity(
        set_a: Set[str],
        set_b: Set[str],
    ) -> float:
        """Compute Jaccard similarity between two sets of tokens.

        Args:
            set_a: First set of tokens.
            set_b: Second set of tokens.

        Returns:
            Jaccard similarity score.
        """
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)

    # ------------------------------------------------------------------
    # PageRank algorithm
    # ------------------------------------------------------------------
    def _page_rank(
        self,
        similarity_matrix: npt.NDArray[np.float64],
    ) -> npt.NDArray[np.float64]:
        """Run the PageRank algorithm on the similarity matrix.

        Args:
            similarity_matrix: Square matrix of sentence similarities.

        Returns:
            Array of PageRank scores for each sentence.

        Raises:
            ValueError: If matrix is not square or empty.
        """
        n = similarity_matrix.shape[0]
        if n == 0:
            return np.array([], dtype=np.float64)
        if similarity_matrix.shape[0] != similarity_matrix.shape[1]:
            raise ValueError("Similarity matrix must be square.")

        # Normalise rows to sum to 1 (handles dangling nodes)
        row_sums = similarity_matrix.sum(axis=1)
        # Avoid division by zero
        row_sums[row_sums == 0] = 1.0
        transition_matrix = similarity_matrix / row_sums[:, np.newaxis]

        # PageRank iterative computation
        d = self._damping_factor
        teleport = (1.0 - d) / n
        scores = np.full(n, 1.0 / n, dtype=np.float64)

        for iteration in range(self._max_iterations):
            prev_scores = scores.copy()
            scores = teleport + d * transition_matrix.T @ scores
            delta = np.abs(scores - prev_scores).sum()
            if delta < self._tolerance:
                logger.debug("PageRank converged in %d iterations.", iteration + 1)
                break
        else:
            logger.warning(
                "PageRank did not converge within %d iterations (delta=%.6f).",
                self._max_iterations,
                delta,
            )

        return scores

# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------
def summarize(
    text: str,
    num_sentences: int = _DEFAULT_NUM_SENTENCES,
    model: str = _DEFAULT_MODEL,
) -> list[str]:
    """Quick‑use function to generate a summary with default parameters.

    Creates a temporary TextRankSummarizer instance.

    Args:
        text: The input text.
        num_sentences: Number of sentences in the summary.
        model: spaCy model name.

    Returns:
        List of summary sentences.

    Raises:
        SummarizerError: If any error occurs during summarization.
    """
    summarizer = TextRankSummarizer(model=model, num_sentences=num_sentences)
    return summarizer.summarize(text)

# ---------------------------------------------------------------------------
# Module entry point (for testing)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    example_text = (
        "The quick brown fox jumps over the lazy dog. "
        "This is a simple sentence. "
        "Machine learning is transforming the world. "
        "Natural language processing is a fascinating field. "
        "We use TextRank to extract the most important sentences. "
        "This summary will contain the top sentences. "
        "The lazy dog sleeps all day. "
        "Artificial intelligence is the future."
    )

    try:
        summary = summarize(example_text, num_sentences=3)
        print("=== Summary ===")
        for i, sent in enumerate(summary, 1):
            print(f"{i}. {sent}")
    except SummarizerError as e:
        logger.error("Summarization failed: %s", e)
        sys.exit(1)