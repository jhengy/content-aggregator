# src/utils.py
"""Shared utility functions for the Daily Content Summary pipeline.

Provides production-grade logging, date/time handling, and safe file I/O
operations used by the fetcher, summarizer, and reporter components.
"""

import json
import logging
import logging.handlers
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(
    name: str = "content_pipeline",
    level: int = logging.INFO,
    log_dir: Optional[Union[str, Path]] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> logging.Logger:
    """Configure a logger with console and optional rotating file handlers.

    Args:
        name: Logger name, typically the component name (e.g., 'fetcher').
        level: Logging level (e.g., logging.DEBUG, logging.INFO).
        log_dir: Directory for log files. If None, only console logging is used.
        max_bytes: Maximum size of each log file before rotation.
        backup_count: Number of rotated log files to keep.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()  # Avoid duplicate handlers on reconfiguration

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler (always)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_dir:
        log_path = Path(log_dir) / f"{name}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ---------------------------------------------------------------------------
# Date / Time Handling
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def format_date_iso(dt: Optional[datetime] = None) -> str:
    """Return an ISO-8601 date string (e.g., '2026-05-29').

    Args:
        dt: A datetime object. Defaults to UTC now.

    Returns:
        Date string in YYYY-MM-DD format.
    """
    if dt is None:
        dt = now_utc()
    return dt.strftime("%Y-%m-%d")


def format_timestamp_iso(dt: Optional[datetime] = None) -> str:
    """Return an ISO-8601 timestamp string with timezone offset.

    Args:
        dt: A datetime object. Defaults to UTC now.

    Returns:
        Timestamp string like '2026-05-29T12:00:01+00:00'.
    """
    if dt is None:
        dt = now_utc()
    # Use isoformat() with timezone; ensure UTC offset shows as +00:00
    return dt.isoformat()


def parse_date_iso(date_str: str) -> datetime:
    """Parse an ISO-8601 date string into a timezone-aware datetime.

    Accepts formats like '2026-05-29' or '2026-05-29T12:00:01+00:00'.
    If no timezone is provided, UTC is assumed.

    Args:
        date_str: Date string in a common ISO format.

    Returns:
        Parsed datetime (always timezone-aware, UTC).

    Raises:
        ValueError: If the string cannot be parsed.
    """
    # Try full ISO timestamp first, then date-only
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse date string: {date_str!r}. "
        "Expected format: 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM:SS±HH:MM'."
    )


def date_range(start: datetime, end: datetime) -> List[str]:
    """Generate a list of ISO date strings between *start* and *end* inclusive.

    Args:
        start: Start datetime.
        end: End datetime (must be after start).

    Returns:
        Sorted list of date strings in YYYY-MM-DD format.

    Raises:
        ValueError: If end is before start.
    """
    if end < start:
        raise ValueError("End date must be after start date.")
    dates: List[str] = []
    current = start.replace(hour=0, minute=0, second=0, microsecond=0)
    end_floor = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while current <= end_floor:
        dates.append(current.strftime("%Y-%m-%d"))
        current += __import__("datetime").timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def ensure_directory(path: Union[str, Path]) -> Path:
    """Create the directory if it doesn't exist; return the Path object.

    Args:
        path: Directory path as string or Path.

    Returns:
        Path object pointing to the (now existing) directory.
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text(filepath: Union[str, Path], encoding: str = "utf-8") -> str:
    """Read a text file and return its contents.

    Args:
        filepath: Path to the file.
        encoding: File encoding (default utf-8).

    Returns:
        File content as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: On read errors.
    """
    path = Path(filepath)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding=encoding)


def write_text(
    content: str,
    filepath: Union[str, Path],
    encoding: str = "utf-8",
    ensure_parent: bool = True,
) -> Path:
    """Write a string to a text file.

    Args:
        content: String to write.
        filepath: Destination path.
        encoding: File encoding (default utf-8).
        ensure_parent: If True, create parent directories automatically.

    Returns:
        Path of the written file.

    Raises:
        IOError: On write errors.
    """
    path = Path(filepath)
    if ensure_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)
    return path


def read_json(filepath: Union[str, Path], encoding: str = "utf-8") -> Any:
    """Read and parse a JSON file.

    Args:
        filepath: Path to the JSON file.
        encoding: File encoding.

    Returns:
        Parsed JSON data (typically dict or list).

    Raises:
        FileNotFoundError, json.JSONDecodeError.
    """
    content = read_text(filepath, encoding=encoding)
    return json.loads(content)


def write_json(
    data: Any,
    filepath: Union[str, Path],
    encoding: str = "utf-8",
    indent: int = 2,
    ensure_ascii: bool = False,
    ensure_parent: bool = True,
) -> Path:
    """Write data as pretty-printed JSON to a file.

    Args:
        data: Python object to serialize.
        filepath: Destination path.
        encoding: File encoding.
        indent: Indentation level (default 2 spaces).
        ensure_ascii: If True, all non-ASCII chars are escaped.
        ensure_parent: If True, create parent directories automatically.

    Returns:
        Path of the written file.

    Raises:
        TypeError: If data is not JSON-serializable.
        IOError: On write errors.
    """
    content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
    return write_text(content, filepath, encoding=encoding, ensure_parent=ensure_parent)


def safe_filename(text: str, max_length: int = 64) -> str:
    """Convert a string into a safe filename (alphanumeric, underscores, dashes).

    Args:
        text: Input string (e.g., a title or slug).
        max_length: Maximum length of the returned filename (without extension).

    Returns:
        Sanitised filename string (may be truncated).
    """
    safe_chars = []
    for ch in text:
        if ch.isalnum() or ch in ("-", "_", "."):
            safe_chars.append(ch)
        elif ch in (" ", " "):  # normal space and non-breaking space
            safe_chars.append("_")
        else:
            safe_chars.append("_")
    filename = "".join(safe_chars).strip("_")
    if not filename:
        filename = "untitled"
    return filename[:max_length]


# ---------------------------------------------------------------------------
# Misc Helpers
# ---------------------------------------------------------------------------

def truncate_text(text: str, max_chars: int = 200, suffix: str = "...") -> str:
    """Truncate text to *max_chars* characters, appending *suffix* if cut.

    Args:
        text: Input text.
        max_chars: Maximum number of characters to keep.
        suffix: String appended when truncation occurs.

    Returns:
        Truncated string.
    """
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(suffix)].rstrip() + suffix