"""
Unit tests for the fetcher module.

Tests cover fetching from NewsAPI and Reddit, error handling,
configuration parsing, and edge cases (empty, malformed responses).
"""

import json
from unittest import mock
from datetime import datetime

import pytest
import requests

from fetcher import (
    fetch_from_newsapi,
    fetch_from_reddit,
    fetch_all_sources,
    load_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_newsapi_response():
    """A typical successful NewsAPI top-headlines response."""
    return {
        "status": "ok",
        "totalResults": 2,
        "articles": [
            {
                "source": {"id": "cnn", "name": "CNN"},
                "author": "John Doe",
                "title": "Test News Article 1",
                "description": "A test article description.",
                "url": "https://example.com/news/1",
                "urlToImage": "https://example.com/img1.jpg",
                "publishedAt": "2026-05-29T10:00:00Z",
                "content": "Full content of article 1...",
            },
            {
                "source": {"id": "bbc", "name": "BBC"},
                "author": "Jane Smith",
                "title": "Test News Article 2",
                "description": "Another test article.",
                "url": "https://example.com/news/2",
                "urlToImage": "https://example.com/img2.jpg",
                "publishedAt": "2026-05-29T11:00:00Z",
                "content": "Full content of article 2...",
            },
        ],
    }


@pytest.fixture
def sample_reddit_response():
    """A typical successful Reddit JSON response for a subreddit listing."""
    return {
        "kind": "Listing",
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "title": "Reddit Post 1",
                        "selftext": "This is the body of Reddit post 1.",
                        "url": "https://reddit.com/r/ai/post1",
                        "score": 150,
                        "num_comments": 25,
                        "created_utc": 1717000000,
                        "subreddit": "artificial",
                        "author": "u/author1",
                    },
                },
                {
                    "kind": "t3",
                    "data": {
                        "title": "Reddit Post 2",
                        "selftext": "Body of Reddit post 2.",
                        "url": "https://reddit.com/r/ai/post2",
                        "score": 88,
                        "num_comments": 10,
                        "created_utc": 1717000100,
                        "subreddit": "artificial",
                        "author": "u/author2",
                    },
                },
            ],
        },
    }


@pytest.fixture
def sample_config_dict():
    """Sample parsed configuration dictionary."""
    return {
        "sources": {
            "newsapi": {
                "api_key": "test_newsapi_key",
                "query": "AI",
                "language": "en",
                "page_size": 10,
            },
            "reddit": {
                "client_id": "test_client_id",
                "client_secret": "test_client_secret",
                "user_agent": "test_user_agent",
                "subreddits": ["artificial", "MachineLearning"],
                "limit": 25,
                "sort": "hot",
            },
        },
        "output": {
            "filename_prefix": "daily_summary",
            "output_dir": "./reports",
        },
    }


# ---------------------------------------------------------------------------
# Tests for fetch_from_newsapi
# ---------------------------------------------------------------------------

class TestFetchFromNewsAPI:
    """Tests for the NewsAPI fetcher."""

    def test_successful_fetch(self, requests_mock, sample_newsapi_response):
        """Should return parsed articles on a 200 response."""
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, json=sample_newsapi_response, status_code=200)

        config = {
            "api_key": "key123",
            "query": "AI",
            "language": "en",
            "page_size": 5,
        }
        articles = fetch_from_newsapi(config)

        assert len(articles) == 2
        assert articles[0]["title"] == "Test News Article 1"
        assert articles[0]["source"] == "CNN"
        assert articles[1]["title"] == "Test News Article 2"
        assert articles[1]["source"] == "BBC"

    def test_api_error(self, requests_mock):
        """Should raise an exception when NewsAPI returns an error status."""
        error_response = {
            "status": "error",
            "code": "apiKeyInvalid",
            "message": "Your API key is invalid.",
        }
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, json=error_response, status_code=401)

        config = {"api_key": "bad_key", "query": "AI"}
        with pytest.raises(RuntimeError, match="NewsAPI error: apiKeyInvalid"):
            fetch_from_newsapi(config)

    def test_http_error(self, requests_mock):
        """Should raise an exception when HTTP status is not 2xx."""
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, status_code=500)

        config = {"api_key": "key", "query": "AI"}
        with pytest.raises(requests.exceptions.HTTPError):
            fetch_from_newsapi(config)

    def test_network_error(self, requests_mock):
        """Should propagate network-level exceptions."""
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, exc=requests.exceptions.ConnectionError)

        config = {"api_key": "key", "query": "AI"}
        with pytest.raises(requests.exceptions.ConnectionError):
            fetch_from_newsapi(config)

    def test_empty_response(self, requests_mock):
        """Should return an empty list when no articles are found."""
        empty_response = {
            "status": "ok",
            "totalResults": 0,
            "articles": [],
        }
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, json=empty_response, status_code=200)

        config = {"api_key": "key", "query": "Nonexistent"}
        articles = fetch_from_newsapi(config)
        assert articles == []

    def test_missing_fields(self, requests_mock):
        """Should skip articles that lack required fields."""
        malformed = {
            "status": "ok",
            "totalResults": 2,
            "articles": [
                {"title": "No source", "url": "https://example.com"},
                {
                    "source": {"name": "Valid"},
                    "title": "Complete article",
                    "url": "https://example.com/2",
                },
            ],
        }
        url = "https://newsapi.org/v2/everything"
        requests_mock.get(url, json=malformed, status_code=200)

        config = {"api_key": "key", "query": "test", "page_size": 10}
        articles = fetch_from_newsapi(config)
        # Only the second article has a source name
        assert len(articles) == 1
        assert articles[0]["title"] == "Complete article"


# ---------------------------------------------------------------------------
# Tests for fetch_from_reddit
# ---------------------------------------------------------------------------

class TestFetchFromReddit:
    """Tests for the Reddit fetcher."""

    def test_successful_fetch(self, requests_mock, sample_reddit_response):
        """Should return parsed posts from a given subreddit."""
        subreddit = "artificial"
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        requests_mock.get(
            url,
            json=sample_reddit_response,
            status_code=200,
            headers={"Content-Type": "application/json"},
        )

        config = {
            "client_id": "cid",
            "client_secret": "cs",
            "user_agent": "test",
            "subreddits": [subreddit],
            "limit": 25,
            "sort": "hot",
        }
        posts = fetch_from_reddit(config)

        assert len(posts) == 2
        assert posts[0]["title"] == "Reddit Post 1"
        assert posts[0]["source"] == "reddit"
        assert posts[1]["title"] == "Reddit Post 2"

    def test_rate_limit(self, requests_mock):
        """Should raise an exception when Reddit rate-limits the request."""
        subreddit = "artificial"
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        requests_mock.get(
            url,
            status_code=429,
            headers={"x-ratelimit-remaining": "0"},
        )

        config = {
            "client_id": "cid",
            "client_secret": "cs",
            "user_agent": "test",
            "subreddits": [subreddit],
        }
        with pytest.raises(RuntimeError, match="Reddit rate limit exceeded"):
            fetch_from_reddit(config)

    def test_invalid_subreddit(self, requests_mock):
        """Should raise an exception if subreddit does not exist."""
        subreddit = "nonexistent99999"
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        requests_mock.get(url, status_code=404)

        config = {
            "client_id": "cid",
            "client_secret": "cs",
            "user_agent": "test",
            "subreddits": [subreddit],
        }
        with pytest.raises(RuntimeError, match="Subreddit not found"):
            fetch_from_reddit(config)

    def test_empty_subreddit(self, requests_mock):
        """Should return an empty list if subreddit has no posts."""
        empty_response = {"kind": "Listing", "data": {"children": []}}
        subreddit = "empty_sub"
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        requests_mock.get(url, json=empty_response, status_code=200)

        config = {
            "client_id": "cid",
            "client_secret": "cs",
            "user_agent": "test",
            "subreddits": [subreddit],
            "limit": 10,
            "sort": "hot",
        }
        posts = fetch_from_reddit(config)
        assert posts == []

    def test_pagination_limit(self, requests_mock):
        """Should respect the limit parameter when fetching posts."""
        subreddit = "testsub"
        url = f"https://www.reddit.com/r/{subreddit}/hot.json"
        # Provide more posts than the limit
        many_posts = {
            "kind": "Listing",
            "data": {
                "children": [
                    {"kind": "t3", "data": {"title": f"Post {i}", "url": f"/r/testsub/{i}"}}
                    for i in range(30)
                ]
            },
        }
        requests_mock.get(url, json=many_posts, status_code=200)

        config = {
            "client_id": "cid",
            "client_secret": "cs",
            "user_agent": "test",
            "subreddits": [subreddit],
            "limit": 15,
            "sort": "hot",
        }
        posts = fetch_from_reddit(config)
        assert len(posts) == 15


# ---------------------------------------------------------------------------
# Tests for configuration loading
# ---------------------------------------------------------------------------

class TestLoadConfig:
    """Tests for the YAML configuration loader."""

    def test_load_valid_config(self, tmp_path):
        """Should correctly parse a well-formed YAML file."""
        config_content = """
sources:
  newsapi:
    api_key: test_key
    query: AI
  reddit:
    client_id: test_cid
    client_secret: test_cs
    user_agent: test_ua
    subreddits:
      - artificial
output:
  filename_prefix: summary
  output_dir: /tmp/reports
"""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(config_content)

        config = load_config(str(config_file))
        assert config["sources"]["newsapi"]["api_key"] == "test_key"
        assert config["sources"]["reddit"]["subreddits"] == ["artificial"]
        assert config["output"]["filename_prefix"] == "summary"

    def test_missing_config_file(self):
        """Should raise FileNotFoundError if the config file does not exist."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_empty_config(self, tmp_path):
        """Should raise ValueError if the config file is empty."""
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        with pytest.raises(ValueError, match="Configuration file is empty"):
            load_config(str(config_file))

    def test_missing_required_keys(self, tmp_path):
        """Should raise KeyError if essential source keys are missing."""
        config_content = "output:\n  filename_prefix: test\n"
        config_file = tmp_path / "minimal.yaml"
        config_file.write_text(config_content)
        with pytest.raises(KeyError, match="sources"):
            load_config(str(config_file))


# ---------------------------------------------------------------------------
# Tests for fetch_all_sources integration
# ---------------------------------------------------------------------------

class TestFetchAllSources:
    """Tests for the combined fetcher that calls multiple sources."""

    def test_fetch_all_success(self, requests_mock, sample_newsapi_response, sample_reddit_response):
        """Should aggregate articles from all configured sources."""
        # Mock NewsAPI
        requests_mock.get(
            "https://newsapi.org/v2/everything?q=AI&language=en&pageSize=10",
            json=sample_newsapi_response,
            status_code=200,
        )
        # Mock Reddit (two subreddits)
        requests_mock.get(
            "https://www.reddit.com/r/artificial/hot.json?limit=25",
            json=sample_reddit_response,
            status_code=200,
        )
        requests_mock.get(
            "https://www.reddit.com/r/MachineLearning/hot.json?limit=25",
            json=sample_reddit_response,
            status_code=200,
        )

        config = {
            "newsapi": {"api_key": "key", "query": "AI", "language": "en", "page_size": 10},
            "reddit": {
                "client_id": "cid",
                "client_secret": "cs",
                "user_agent": "test",
                "subreddits": ["artificial", "MachineLearning"],
                "limit": 25,
                "sort": "hot",
            },
        }

        articles = fetch_all_sources(config)
        # 2 from NewsAPI + 2 from artificial + 2 from MachineLearning = 6
        assert len(articles) == 6
        assert all("title" in a and "source" in a for a in articles)

    def test_partial_source_failure(self, requests_mock):
        """Should still return results from working sources if one fails."""
        requests_mock.get(
            "https://newsapi.org/v2/everything?q=AI&language=en&pageSize=10",
            status_code=500,
        )
        requests_mock.get(
            "https://www.reddit.com/r/artificial/hot.json?limit=25",
            json={"kind": "Listing", "data": {"children": []}},
            status_code=200,
        )

        config = {
            "newsapi": {"api_key": "bad", "query": "AI", "language": "en", "page_size": 10},
            "reddit": {
                "client_id": "cid",
                "client_secret": "cs",
                "user_agent": "test",
                "subreddits": ["artificial"],
                "limit": 25,
                "sort": "hot",
            },
        }

        articles = fetch_all_sources(config)
        # Reddit returned empty list, NewsAPI failed – should be empty
        assert articles == []

    def test_no_sources_configured(self):
        """Should return an empty list when no source config is provided."""
        config = {}
        articles = fetch_all_sources(config)
        assert articles == []