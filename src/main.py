#!/usr/bin/env python3
"""
src/main.py - Daily Content Summary Pipeline

Orchestrates the three-stage pipeline: fetch raw articles, generate extractive
summary, and publish as a Markdown report. Uses YAML configuration and
environment variables for API keys.

Production-ready enhancements:
- Full type annotations (Python 3.9+ compatible)
- Comprehensive error handling with specific exceptions
- Detailed docstrings (Google style)
- Proper logging with rotation support
- Input validation and sanitisation
- Performance optimisations (requests.Session, tokenisation caching)
- Clean code with single responsibility principle
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
import logging.handlers
import os
import re
import sys
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from string import punctuation
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import yaml
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PACKAGE_NAME: str = "daily_summary"
DEFAULT_CONFIG: str = "config.yaml"
DEFAULT_MAX_SENTENCES: int = 10
DEFAULT_TIMEOUT: int = 15
MAX_CONTENT_LENGTH: int = 100_000  # characters
MIN_SENTENCE_LENGTH: int = 10
MAX_RETRIES: int = 3
RETRY_BACKOFF: float = 2.0
USER_AGENT: str = "DailySummaryPipeline/1.0 (production)"
FREQUENCY_METHOD: str = "frequency"
TOP_N_WORDS: int = 100

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
_logger: logging.Logger = logging.getLogger(PACKAGE_NAME)


def setup_logging(level: str = "INFO") -> None:
    """Configure logging with rotating file handler and console output.

    Args:
        level: Logging level string (e.g. "DEBUG", "INFO").
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    _logger.setLevel(numeric_level)

    # Prevent duplicate handlers
    if _logger.handlers:
        return

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)
    _logger.addHandler(console_handler)

    # Rotating file handler (optional, only if logs directory exists)
    log_dir = Path("logs")
    if log_dir.exists():
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{PACKAGE_NAME}.log",
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_fmt = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
        )
        file_handler.setFormatter(file_fmt)
        _logger.addHandler(file_handler)

    _logger.debug("Logging initialised at level %s", level)


# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------
class ConfigError(Exception):
    """Raised when configuration is invalid or missing required fields."""


class FetchError(Exception):
    """Raised when fetching articles fails."""


class SummarizationError(Exception):
    """Raised when summarization fails."""


class ReportError(Exception):
    """Raised when report generation or writing fails."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
class Config:
    """Loads, validates and provides typed access to pipeline configuration.

    Expected structure (YAML):
        fetcher:
          sources: ["newsapi"]
          newsapi_key_env: "NEWSAPI_KEY"
        summarizer:
          method: "frequency"
          max_sentences: 10
        reporter:
          output_dir: "output"
          filename_prefix: "daily_summary"
    """

    def __init__(self, config_path: str) -> None:
        self._config_path: str = config_path
        self._data: Dict[str, Any] = {}
        self._load()
        self._validate()

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------
    def get(self, *keys: str, default: Any = None) -> Any:
        """Retrieve a nested config value by key path.

        Args:
            *keys: Sequence of keys describing the path.
            default: Value returned if path does not exist.

        Returns:
            The value at the given path, or *default*.
        """
        result: Any = self._data
        for key in keys:
            if isinstance(result, dict):
                result = result.get(key, default)
            else:
                return default
        return result if result is not None else default

    @property
    def fetcher_sources(self) -> List[str]:
        return self.get("fetcher", "sources", default=["newsapi"])

    @property
    def newsapi_key_env(self) -> str:
        return self.get("fetcher", "newsapi_key_env", default="NEWSAPI_KEY")

    @property
    def summarizer_method(self) -> str:
        return self.get("summarizer", "method", default=FREQUENCY_METHOD)

    @property
    def max_sentences(self) -> int:
        return int(self.get("summarizer", "max_sentences", default=DEFAULT_MAX_SENTENCES))

    @property
    def output_dir(self) -> str:
        return self.get("reporter", "output_dir", default="output")

    @property
    def filename_prefix(self) -> str:
        return self.get("reporter", "filename_prefix", default="daily_summary")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        """Load YAML config from file path. Falls back to defaults if missing."""
        cfg_path = Path(self._config_path)
        if not cfg_path.exists():
            _logger.warning("Configuration file '%s' not found. Using built-in defaults.", cfg_path)
            self._data = {
                "fetcher": {"sources": ["newsapi"], "newsapi_key_env": "NEWSAPI_KEY"},
                "summarizer": {"method": FREQUENCY_METHOD, "max_sentences": DEFAULT_MAX_SENTENCES},
                "reporter": {"output_dir": "output", "filename_prefix": "daily_summary"},
            }
            return

        try:
            with cfg_path.open("r", encoding="utf-8") as fh:
                loaded = yaml.safe_load(fh)
            self._data = loaded if isinstance(loaded, dict) else {}
            _logger.info("Configuration loaded from '%s'", cfg_path)
        except (yaml.YAMLError, IOError) as exc:
            raise ConfigError(f"Failed to load config file '{cfg_path}': {exc}") from exc

    def _validate(self) -> None:
        """Basic validation of configuration values.

        Raises:
            ConfigError: If required fields are missing or malformed.
        """
        if not self._data:
            _logger.warning("Empty configuration – will use defaults where possible")
            return

        errors: List[str] = []

        # Validate fetcher section
        fetcher = self._data.get("fetcher", {})
        if fetcher:
            sources = fetcher.get("sources")
            if sources is not None:
                if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
                    errors.append("'fetcher.sources' must be a list of strings")
            newsapi_key_env = fetcher.get("newsapi_key_env")
            if newsapi_key_env is not None and not isinstance(newsapi_key_env, str):
                errors.append("'fetcher.newsapi_key_env' must be a string")

        # Validate summarizer section
        summarizer = self._data.get("summarizer", {})
        if summarizer:
            method = summarizer.get("method")
            if method is not None and method not in (FREQUENCY_METHOD,):
                errors.append(f"'summarizer.method' must be '{FREQUENCY_METHOD}' (only method supported)")
            max_sentences = summarizer.get("max_sentences")
            if max_sentences is not None:
                try:
                    ms = int(max_sentences)
                    if ms < 1:
                        errors.append("'summarizer.max_sentences' must be at least 1")
                except (ValueError, TypeError):
                    errors.append("'summarizer.max_sentences' must be an integer")

        # Validate reporter section
        reporter = self._data.get("reporter", {})
        if reporter:
            output_dir = reporter.get("output_dir")
            if output_dir is not None and not isinstance(output_dir, str):
                errors.append("'reporter.output_dir' must be a string")
            filename_prefix = reporter.get("filename_prefix")
            if filename_prefix is not None and not isinstance(filename_prefix, str):
                errors.append("'reporter.filename_prefix' must be a string")

        if errors:
            raise ConfigError("Configuration validation failed: " + "; ".join(errors))

        _logger.info("Configuration validated successfully.")


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------
class Fetcher:
    """Fetch articles from configured sources (currently only NewsAPI)."""

    NEWSAPI_BASE_URL: str = "https://newsapi.org/v2/top-headlines"

    def __init__(self, config: Config) -> None:
        self._config: Config = config
        self._session: requests.Session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create a requests.Session with retry and timeout configuration.

        Returns:
            Configured session instance.
        """
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

        retry_strategy = Retry(
            total=MAX_RETRIES,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def _get_api_key(self) -> str:
        """Retrieve the NewsAPI key from environment variable.

        Returns:
            API key string.

        Raises:
            FetchError: If the environment variable is missing or empty.
        """
        env_var = self._config.newsapi_key_env
        api_key = os.environ.get(env_var)
        if not api_key:
            raise FetchError(f"NewsAPI key not found in environment variable '{env_var}'")
        return api_key

    def _sanitise_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitise and normalise a single article dictionary.

        Args:
            article: Raw article dict from API.

        Returns:
            Cleaned article dict with required string fields.
        """
        sanitised: Dict[str, Any] = {
            "title": str(article.get("title", "") or "").strip(),
            "description": str(article.get("description", "") or "").strip(),
            "content": str(article.get("content", "") or "").strip(),
            "url": str(article.get("url", "") or "").strip(),
            "source": str(article.get("source", {}).get("name", "Unknown") or "Unknown"),
            "published_at": str(article.get("publishedAt", "") or "").strip(),
        }
        return sanitised

    def fetch(self) -> List[Dict[str, Any]]:
        """Fetch top headlines from NewsAPI.

        Returns:
            List of sanitised article dictionaries.

        Raises:
            FetchError: On network errors, non-200 responses, or missing API key.
        """
        api_key = self._get_api_key()
        params: Dict[str, Any] = {
            "apiKey": api_key,
            "pageSize": 50,
            "language": "en",
        }

        try:
            _logger.info("Fetching articles from NewsAPI (source filter: %s)", self._config.fetcher_sources)
            response = self._session.get(
                self.NEWSAPI_BASE_URL,
                params=params,
                timeout=DEFAULT_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            raise FetchError(f"Failed to fetch articles from NewsAPI: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise FetchError(f"Invalid JSON response from NewsAPI: {exc}") from exc

        articles_raw = data.get("articles", [])
        if not isinstance(articles_raw, list):
            raise FetchError("NewsAPI response 'articles' field is not a list")

        # Filter sources if configured
        sources_filter = self._config.fetcher_sources
        if sources_filter and "newsapi" not in sources_filter:
            _logger.info("No matching source enabled; returning empty list.")
            return []

        articles: List[Dict[str, Any]] = [self._sanitise_article(a) for a in articles_raw]
        articles = [a for a in articles if a["title"] or a["description"] or a["content"]]
        _logger.info("Fetched and sanitised %d articles", len(articles))
        return articles


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------
class Summarizer:
    """Generate extractive summaries using word frequency scoring."""

    # Simple English stopwords (lowercase)
    STOPWORDS: Set[str] = {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "by", "with", "from", "is", "are", "was", "were", "be", "been",
        "being", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "shall", "can", "need", "dare",
        "ought", "used", "this", "that", "these", "those", "i", "you", "he",
        "she", "it", "we", "they", "my", "your", "his", "her", "its", "our",
        "their", "me", "him", "us", "them", "not", "no", "nor", "so", "if",
        "then", "else", "when", "where", "why", "how", "all", "each", "every",
        "both", "few", "more", "most", "other", "some", "such", "only", "own",
        "same", "too", "very", "just", "because", "as", "until", "while",
        "about", "between", "through", "during", "before", "after", "above",
        "below", "up", "down", "out", "off", "over", "under", "again", "further",
        "once", "here", "there", "what", "which", "who", "whom", "whose",
    }

    def __init__(self, config: Config) -> None:
        self._max_sentences: int = config.max_sentences
        self._method: str = config.summarizer_method

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into sentences using a simple regex.

        Args:
            text: Input text.

        Returns:
            List of sentence strings.
        """
        # Split on sentence-ending punctuation followed by space or end of string
        sentences = re.split(r'(?<=[.!?])\s+', text)
        # Further split on newlines
        result: List[str] = []
        for s in sentences:
            result.extend(s.split('\n'))
        # Clean and filter
        cleaned = [s.strip() for s in result if s.strip()]
        return cleaned

    @staticmethod
    def _tokenise(text: str) -> List[str]:
        """Tokenise text into lowercase alphanumeric words.

        Args:
            text: Input text.

        Returns:
            List of word tokens.
        """
        # Use regex to capture only letters, digits, and apostrophes (e.g., don't)
        words = re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())
        return words

    @lru_cache(maxsize=256)
    def _compute_word_frequencies(self, text: str) -> Counter:
        """Compute word frequencies for a given text, excluding punctuation and stopwords.

        Args:
            text: Input text (cached).

        Returns:
            Counter of word frequencies.
        """
        words = self._tokenise(text)
        filtered = [
            word for word in words
            if word not in self.STOPWORDS and word not in punctuation
        ]
        return Counter(filtered)

    def summarize(self, articles: List[Dict[str, Any]]) -> str:
        """Generate an extractive summary from a list of articles.

        Uses word frequency scoring to select the most informative sentences.

        Args:
            articles: List of article dictionaries with 'title', 'description', 'content'.

        Returns:
            Summary text as a single string.

        Raises:
            SummarizationError: If summarization fails (e.g., no content).
        """
        if not articles:
            _logger.warning("No articles to summarise.")
            return ""

        try:
            # Combine article content into a single corpus
            corpus_parts: List[str] = []
            for article in articles:
                title = article.get("title", "")
                description = article.get("description", "")
                content = article.get("content", "")
                # Limit content length to prevent memory issues
                if len(content) > MAX_CONTENT_LENGTH:
                    content = content[:MAX_CONTENT_LENGTH]
                corpus_parts.append(f"{title}. {description}. {content}")

            corpus = " ".join(corpus_parts)

            # Tokenise and compute word frequencies
            word_freq = self._compute_word_frequencies(corpus)

            # Split into sentences
            sentences = self._split_sentences(corpus)
            if not sentences:
                return ""

            # Score each sentence based on sum of word frequencies (normalised by length)
            sentence_scores: List[Tuple[float, int, str]] = []
            for idx, sentence in enumerate(sentences):
                words = self._tokenise(sentence)
                if len(words) < 3:
                    continue
                score = sum(word_freq.get(w, 0) for w in words) / max(len(words), 1)
                sentence_scores.append((score, idx, sentence))

            # Select top N sentences while preserving original order
            top_sentences = heapq.nlargest(
                self._max_sentences,
                sentence_scores,
                key=lambda x: (x[0], -x[1])
            )
            # Sort by original index to maintain flow
            top_sentences.sort(key=lambda x: x[1])
            summary = " ".join(s[2] for s in top_sentences)

            _logger.info(
                "Generated summary with %d sentences from %d articles",
                len(top_sentences),
                len(articles),
            )
            return summary

        except Exception as exc:
            raise SummarizationError(f"Summarisation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------
class Reporter:
    """Generate and write Markdown report files."""

    def __init__(self, config: Config) -> None:
        self._output_dir: str = config.output_dir
        self._prefix: str = config.filename_prefix

    def _validate_output_dir(self) -> Path:
        """Validate and create output directory if needed.

        Returns:
            Path object pointing to the output directory.

        Raises:
            ReportError: If directory cannot be created or is unsafe.
        """
        dir_path = Path(self._output_dir).resolve()
        # Prevent path traversal
        if ".." in self._output_dir or str(dir_path) != str(Path(self._output_dir).resolve()):
            raise ReportError(f"Unsafe output directory path: '{self._output_dir}'")
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            _logger.debug("Output directory ensured: '%s'", dir_path)
            return dir_path
        except OSError as exc:
            raise ReportError(f"Cannot create output directory '{dir_path}': {exc}") from exc

    def _build_report(
        self,
        articles: List[Dict[str, Any]],
        summary: str,
        date: datetime.date,
    ) -> str:
        """Build Markdown report content.

        Args:
            articles: List of articles used.
            summary: Generated summary text.
            date: Report date.

        Returns:
            Markdown string.
        """
        lines: List[str] = []
        lines.append(f"# 📰 Daily Content Summary - {date.isoformat()}")
        lines.append("")
        lines.append("## Executive Summary")
        lines.append("")
        lines.append(summary if summary else "*No summary generated.*")
        lines.append("")
        lines.append("## Sources")
        lines.append("")
        for idx, article in enumerate(articles, 1):
            title = article.get("title", "Untitled")
            url = article.get("url", "")
            source = article.get("source", "Unknown")
            published = article.get("published_at", "")
            lines.append(f"{idx}. **{title}**")
            if url:
                lines.append(f"   - URL: {url}")
            lines.append(f"   - Source: {source}")
            if published:
                lines.append(f"   - Published: {published}")
            lines.append("")
        lines.append("---")
        lines.append(f"_Generated on {datetime.datetime.now().isoformat()}_")
        return "\n".join(lines)

    def publish(
        self,
        articles: List[Dict[str, Any]],
        summary: str,
        date: Optional[datetime.date] = None,
    ) -> Path:
        """Write the report file to disk.

        Args:
            articles: List of article dictionaries.
            summary: Summary text.
            date: Report date (defaults to today if None).

        Returns:
            Path to the written report file.

        Raises:
            ReportError: If writing fails.
        """
        if date is None:
            date = datetime.date.today()

        report = self._build_report(articles, summary, date)
        output_dir = self._validate_output_dir()
        safe_prefix = re.sub(r'[^a-zA-Z0-9_-]', '_', self._prefix)
        filename = f"{safe_prefix}_{date.isoformat()}.md"
        file_path = output_dir / filename

        try:
            with file_path.open("w", encoding="utf-8") as fh:
                fh.write(report)
            _logger.info("Report written to '%s'", file_path)
            return file_path
        except OSError as exc:
            raise ReportError(f"Failed to write report to '{file_path}': {exc}") from exc


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------
def run_pipeline(config_path: str = DEFAULT_CONFIG) -> int:
    """Execute the full Daily Content Summary pipeline.

    Steps:
        1. Load and validate configuration.
        2. Fetch articles from NewsAPI.
        3. Generate extractive summary.
        4. Write Markdown report.

    Args:
        config_path: Path to YAML configuration file.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    start_time = time.time()
    setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    try:
        # 1. Configuration
        config = Config(config_path)

        # 2. Fetch
        fetcher = Fetcher(config)
        articles = fetcher.fetch()
        if not articles:
            _logger.warning("No articles fetched; pipeline will produce empty report.")

        # 3. Summarise
        summarizer = Summarizer(config)
        summary = summarizer.summarize(articles)

        # 4. Report
        reporter = Reporter(config)
        output_path = reporter.publish(articles, summary)

        elapsed = time.time() - start_time
        _logger.info(
            "Pipeline completed successfully in %.2f seconds. Report: %s",
            elapsed,
            output_path,
        )
        return 0

    except (ConfigError, FetchError, SummarizationError, ReportError) as exc:
        _logger.error("Pipeline failed: %s", exc)
        return 1
    except Exception as exc:
        _logger.exception("Unexpected pipeline error: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Parse command-line arguments and run pipeline."""
    parser = argparse.ArgumentParser(
        description="Daily Content Summary Pipeline",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=DEFAULT_CONFIG,
        help=f"Path to YAML configuration file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: INFO)",
    )
    args = parser.parse_args()

    # Set log level via environment for the pipeline
    os.environ.setdefault("LOG_LEVEL", args.log_level)

    sys.exit(run_pipeline(args.config))


if __name__ == "__main__":
    main()