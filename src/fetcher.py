"""
src/fetcher.py
--------------
Fetches raw articles from configured external news APIs and normalizes responses
into a common Article format. Supports NewsAPI, Reddit, and extensible sources.

Dependencies:
  - requests (>=2.28)
  - (optional) python-dotenv for local env loading

Configuration (YAML shape):
  sources:
    - name: newsapi
      api_key: "${NEWSAPI_KEY}"   # supports env var expansion
      query: "artificial intelligence"
      page_size: 10
    - name: reddit
      client_id: "${REDDIT_CLIENT_ID}"
      client_secret: "${REDDIT_CLIENT_SECRET}"
      user_agent: "DailyContentSummary/1.0"
      subreddit: "artificial"
      limit: 25
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, quote

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalized article schema
# ---------------------------------------------------------------------------

@dataclass
class Article:
    """Standard article representation produced by all fetchers."""
    source: str                    # e.g., "newsapi", "reddit"
    source_id: str                 # original id or permalink
    title: str
    url: str
    published_at: Optional[datetime] = None
    author: Optional[str] = None
    summary: Optional[str] = None   # first ~300 chars of content/selftext
    content: Optional[str] = None   # full body if available
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.published_at:
            d["published_at"] = self.published_at.isoformat()
        return d


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _resolve_env(value: str) -> str:
    """Expand ${VAR} or $VAR patterns with environment variables."""
    if not isinstance(value, str):
        return value
    def replacer(match):
        var = match.group(1) or match.group(2)
        return os.environ.get(var, "")
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', replacer, value)


def _load_source_config(source_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve environment variable placeholders in source configuration."""
    resolved = {}
    for key, val in source_cfg.items():
        if isinstance(val, str):
            resolved[key] = _resolve_env(val)
        elif isinstance(val, dict):
            resolved[key] = _load_source_config(val)
        else:
            resolved[key] = val
    return resolved


# ---------------------------------------------------------------------------
# Retry decorator (simple)
# ---------------------------------------------------------------------------

def retry(max_retries: int = 3, backoff: float = 1.0, retryable_codes: tuple = (429, 500, 502, 503, 504)):
    """Decorator for retrying HTTP requests on transient failures."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (requests.exceptions.RequestException, ConnectionError, TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_time = backoff * (2 ** (attempt - 1))
                        logger.warning("Retry %d/%d after error: %s. Sleeping %.1fs",
                                       attempt, max_retries, e, sleep_time)
                        time.sleep(sleep_time)
                    else:
                        logger.error("All %d retries exhausted for %s", max_retries, func.__name__)
            raise last_exception
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Base Fetcher
# ---------------------------------------------------------------------------

class BaseSourceFetcher:
    """Base class for source-specific fetchers."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def fetch(self) -> List[Article]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# NewsAPI fetcher
# ---------------------------------------------------------------------------

class NewsAPIFetcher(BaseSourceFetcher):
    """Fetch articles from NewsAPI (https://newsapi.org)."""

    BASE_URL = "https://newsapi.org/v2/everything"

    def fetch(self) -> List[Article]:
        api_key = self.config.get("api_key")
        if not api_key:
            logger.error("NewsAPI: missing api_key")
            return []

        params = {
            "apiKey": api_key,
            "q": self.config.get("query", "technology"),
            "pageSize": self.config.get("page_size", 20),
            "language": self.config.get("language", "en"),
            "sortBy": self.config.get("sort_by", "publishedAt"),
        }
        # Optional date range
        if self.config.get("from_date"):
            params["from"] = self.config["from_date"]
        if self.config.get("to_date"):
            params["to"] = self.config["to_date"]

        try:
            response = self._get_with_retry(params)
            data = response.json()
            if data.get("status") != "ok":
                logger.error("NewsAPI error: %s", data.get("message", "unknown"))
                return []
            return [self._normalize_article(a) for a in data.get("articles", [])]
        except Exception as e:
            logger.exception("NewsAPI fetch failed: %s", e)
            return []

    @retry(max_retries=3, backoff=1.0)
    def _get_with_retry(self, params: Dict[str, Any]) -> requests.Response:
        resp = requests.get(self.BASE_URL, params=params, timeout=30)
        resp.raise_for_status()
        return resp

    @staticmethod
    def _normalize_article(article: Dict[str, Any]) -> Article:
        title = article.get("title", "") or ""
        url = article.get("url", "") or ""
        published_str = article.get("publishedAt")
        published = None
        if published_str:
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                pass
        content = article.get("content") or article.get("description") or ""
        # Truncate lengthy content for summary
        summary = content[:300] if content else None
        author = article.get("author")
        # source name from nested obj
        source_name = "unknown"
        if isinstance(article.get("source"), dict):
            source_name = article["source"].get("name", "unknown")
        return Article(
            source="newsapi",
            source_id=url,
            title=title,
            url=url,
            published_at=published,
            author=author,
            summary=summary,
            content=content,
            metadata={"source_name": source_name, "original": article},
        )


# ---------------------------------------------------------------------------
# Reddit fetcher (via JSON endpoint, no PRAW dependency)
# ---------------------------------------------------------------------------

class RedditFetcher(BaseSourceFetcher):
    """Fetch hot/top posts from Reddit as articles using the public JSON API."""

    BASE_URL = "https://www.reddit.com/r/{subreddit}/{sort}.json"

    def fetch(self) -> List[Article]:
        subreddit = self.config.get("subreddit", "artificial")
        sort = self.config.get("sort", "hot")
        limit = min(self.config.get("limit", 25), 100)
        url = self.BASE_URL.format(subreddit=subreddit, sort=sort)
        headers = {
            "User-Agent": self.config.get("user_agent", "DailyContentSummary/1.0")
        }
        params = {"limit": limit, "raw_json": 1}

        # Optional OAuth for higher rate limits
        client_id = self.config.get("client_id")
        client_secret = self.config.get("client_secret")
        auth = None
        if client_id and client_secret:
            auth = (client_id, client_secret)

        try:
            response = self._get_with_retry(url, headers=headers, params=params, auth=auth)
            data = response.json()
            children = data.get("data", {}).get("children", [])
            return [self._normalize_post(child["data"]) for child in children]
        except Exception as e:
            logger.exception("Reddit fetch failed: %s", e)
            return []

    @retry(max_retries=3, backoff=2.0)
    def _get_with_retry(self, url: str, headers: dict, params: dict,
                        auth: Optional[tuple] = None) -> requests.Response:
        resp = requests.get(url, headers=headers, params=params, auth=auth, timeout=30)
        resp.raise_for_status()
        return resp

    @staticmethod
    def _normalize_post(post: Dict[str, Any]) -> Article:
        title = post.get("title", "") or ""
        # Reddit permalink
        permalink = post.get("permalink", "")
        url = f"https://www.reddit.com{permalink}" if permalink else (post.get("url") or "")
        published = None
        created_utc = post.get("created_utc")
        if created_utc:
            published = datetime.fromtimestamp(created_utc, tz=timezone.utc)
        selftext = post.get("selftext", "") or ""
        # Use URL if selftext is empty (link post)
        content = selftext or post.get("url_overridden_by_dest", "")
        summary = (selftext[:300] if selftext else None) or (title[:200])
        author = post.get("author")
        return Article(
            source="reddit",
            source_id=post.get("id", ""),
            title=title,
            url=url,
            published_at=published,
            author=author,
            summary=summary,
            content=content,
            metadata={
                "subreddit": post.get("subreddit"),
                "score": post.get("score"),
                "num_comments": post.get("num_comments"),
                "original": post,
            },
        )


# ---------------------------------------------------------------------------
# Main Fetcher orchestrator
# ---------------------------------------------------------------------------

class Fetcher:
    """
    Top-level fetcher that dispatches to source-specific fetchers based on config.
    Usage:
        config = {
            "sources": [
                {"name": "newsapi", "api_key": "$NEWSAPI_KEY", ...},
                {"name": "reddit", "client_id": "$REDDIT_CLIENT_ID", ...}
            ]
        }
        fetcher = Fetcher(config)
        articles = fetcher.fetch_all()
    """

    SOURCE_MAP = {
        "newsapi": NewsAPIFetcher,
        "reddit": RedditFetcher,
    }

    def __init__(self, config: Dict[str, Any]):
        self.config = config

    def fetch_all(self) -> List[Article]:
        """Iterate over configured sources and collect normalized articles."""
        all_articles: List[Article] = []
        sources = self.config.get("sources", [])
        if not sources:
            logger.warning("No sources configured in fetcher config")
            return all_articles

        for source_cfg in sources:
            name = source_cfg.get("name", "").lower().strip()
            resolved_cfg = _load_source_config(source_cfg)
            fetcher_class = self.SOURCE_MAP.get(name)
            if not fetcher_class:
                logger.warning("Unknown source '%s', skipping", name)
                continue
            fetcher = fetcher_class(resolved_cfg)
            try:
                articles = fetcher.fetch()
                logger.info("Fetched %d articles from %s", len(articles), name)
                all_articles.extend(articles)
            except Exception as e:
                logger.error("Failed to fetch from %s: %s", name, e)

        return all_articles


# ---------------------------------------------------------------------------
# Convenience function for standalone use
# ---------------------------------------------------------------------------

def fetch_from_config(config_path: str) -> List[Article]:
    """
    Load YAML config from file and fetch articles.

    Args:
        config_path: Path to YAML file (optional, if None uses default).

    Returns:
        List of normalized Article dataclass objects.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError(
            "PyYAML is required to load config from file. "
            "Install with: pip install pyyaml"
        )

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    fetcher = Fetcher(config)
    return fetcher.fetch_all()


if __name__ == "__main__":
    # Example: load from config.yaml and print fetched article titles
    logging.basicConfig(level=logging.INFO)
    articles = fetch_from_config("config.yaml")
    for art in articles:
        print(f"[{art.source}] {art.title} ({art.published_at})")
    print(f"\nTotal: {len(articles)} articles")