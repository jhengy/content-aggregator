from typing import TypedDict, Optional

class Article(TypedDict):
    """Type definition for processed article data"""
    url: str
    title: Optional[str]
    author: Optional[str]
    publish_at: Optional[int]  # Unix timestamp
    tags: Optional[str]
    date: Optional[str]  # ISO date string
    summary: Optional[str]
    timestamp: Optional[str]  # Processing timestamp 