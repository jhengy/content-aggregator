"""
src/reporter.py - Generates Markdown or HTML report with executive summary and sources.

Part of the Daily Content Summary pipeline. Takes a validated list of source
dictionaries and an executive summary, then produces a formatted report in
either Markdown or HTML format (with proper escaping for XSS prevention).
Supports optional direct file output and respects configurable line lengths.

Example usage:
    from datetime import date
    from src.reporter import generate_report

    sources = [
        {"title": "Example", "url": "https://example.com", "snippet": "Desc"}
    ]
    report = generate_report(
        report_date=date(2026, 5, 29),
        executive_summary="Latest AI news...",
        sources=sources,
        output_format="markdown",
    )
    print(report)
"""

from __future__ import annotations

import html
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import (
    Any,
    Dict,
    Final,
    List,
    Literal,
    Optional,
    Sequence,
    Tuple,
    Union,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REQUIRED_SOURCE_KEYS: Final[tuple[str, ...]] = ("title", "url")
_ALLOWED_SOURCE_KEYS: Final[frozenset[str]] = frozenset(
    {"title", "url", "snippet", "source_name"}
)
_MAX_LINE_LENGTH: Final[int] = 120
_DEFAULT_ENCODING: Final[str] = "utf-8"
_FORMAT_ALIASES: Final[dict[str, str]] = {
    "markdown": "markdown",
    "md": "markdown",
    "html": "html",
    "htm": "html",
}
_LOG_PREFIX: Final[str] = "[REPORTER]"
_MAX_URL_LENGTH: Final[int] = 2048
_MAX_TITLE_LENGTH: Final[int] = 500

# ---------------------------------------------------------------------------
# Custom Exceptions
# ---------------------------------------------------------------------------


class ReportGenerationError(Exception):
    """Base exception for report generation failures."""


class InvalidSourceError(ValueError):
    """Raised when a source dictionary is missing required fields or contains
    invalid data."""


class InvalidInputError(ValueError):
    """Raised when any input parameter fails validation."""


class OutputWriteError(OSError):
    """Raised when writing the report to disk fails."""


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

SourceDict = Dict[str, str]
OutputFormat = Literal["markdown", "md", "html", "htm"]

# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_sources(sources: Sequence[SourceDict]) -> None:
    """Validate the list of source dictionaries.

    Args:
        sources: List of dictionary objects representing sources.

    Raises:
        InvalidSourceError: If any source is malformed or missing required keys.
    """
    if not sources:
        logger.warning(f"{_LOG_PREFIX} No sources provided; report will have an empty source list.")
        return

    for idx, src in enumerate(sources):
        if not isinstance(src, dict):
            raise InvalidSourceError(
                f"Source at index {idx} must be a dict, got {type(src).__name__}"
            )

        # Check required keys
        missing = [k for k in _REQUIRED_SOURCE_KEYS if k not in src]
        if missing:
            raise InvalidSourceError(
                f"Source at index {idx} missing required key(s): {missing}"
            )

        # Validate allowed keys and types
        for key, value in src.items():
            if key not in _ALLOWED_SOURCE_KEYS:
                raise InvalidSourceError(
                    f"Source at index {idx} contains unknown key '{key}'"
                )
            if not isinstance(value, str):
                raise InvalidSourceError(
                    f"Source at index {idx}, key '{key}' must be a string, "
                    f"got {type(value).__name__}"
                )

        # Sanitize URL (basic validation: must have a scheme and netloc)
        url: str = src.get("url", "").strip()
        if not url:
            raise InvalidSourceError(f"Source at index {idx} has empty 'url'")
        if len(url) > _MAX_URL_LENGTH:
            raise InvalidSourceError(
                f"Source at index {idx} URL exceeds max length {_MAX_URL_LENGTH}"
            )
        if not url.startswith(("http://", "https://", "ftp://", "ftps://")):
            logger.warning(
                f"{_LOG_PREFIX} Source at index {idx} URL does not start with "
                f"a known scheme: {url[:50]}..."
            )

        # Validate title length
        title: str = src.get("title", "").strip()
        if not title:
            raise InvalidSourceError(f"Source at index {idx} has empty 'title'")
        if len(title) > _MAX_TITLE_LENGTH:
            logger.warning(
                f"{_LOG_PREFIX} Source at index {idx} title exceeds max length "
                f"{_MAX_TITLE_LENGTH}, will be truncated"
            )


def _validate_executive_summary(summary: str) -> None:
    """Validate the executive summary string.

    Args:
        summary: The executive summary text.

    Raises:
        InvalidInputError: If summary is empty or not a string.
    """
    if not isinstance(summary, str):
        raise InvalidInputError(
            f"executive_summary must be a string, got {type(summary).__name__}"
        )
    if not summary.strip():
        raise InvalidInputError("executive_summary cannot be empty or whitespace only")


def _validate_report_date(report_date: date) -> None:
    """Validate the report date.

    Args:
        report_date: The date object for the report.

    Raises:
        InvalidInputError: If report_date is not a date instance.
    """
    if not isinstance(report_date, date):
        raise InvalidInputError(
            f"report_date must be a datetime.date instance, "
            f"got {type(report_date).__name__}"
        )


def _validate_format(output_format: str) -> OutputFormat:
    """Normalize and validate the output format string.

    Args:
        output_format: Expected "markdown", "md", "html", or "htm" (case-insensitive).

    Raises:
        InvalidInputError: If format is unknown.

    Returns:
        Normalized format ("markdown" or "html").
    """
    if not isinstance(output_format, str):
        raise InvalidInputError(
            f"output_format must be a string, got {type(output_format).__name__}"
        )
    normalized = output_format.strip().lower()
    result = _FORMAT_ALIASES.get(normalized)
    if result is None:
        raise InvalidInputError(
            f"output_format must be one of {sorted(_FORMAT_ALIASES.keys())}, "
            f"got '{normalized}'"
        )
    return result  # type: ignore[return-value]  # Literal type matches


def _validate_file_path(file_path: Optional[Union[str, Path]]) -> Optional[Path]:
    """Validate and resolve the output file path.

    Args:
        file_path: Optional path string or Path object.

    Raises:
        InvalidInputError: If path is not valid (e.g., directory traversal, not writable).

    Returns:
        Resolved Path object or None if no path provided.
    """
    if file_path is None:
        return None
    try:
        p = Path(file_path).resolve(strict=False)
    except (ValueError, OSError) as exc:
        raise InvalidInputError(f"Invalid file_path: {exc}") from exc

    # Prevent directory traversal leaving intended base directory
    if ".." in str(p):
        raise InvalidInputError(f"file_path contains '..' which is not allowed: {file_path}")

    # Check that parent directory exists and is writable (if not, warning)
    parent = p.parent
    if not parent.exists():
        try:
            parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"{_LOG_PREFIX} Created missing parent directory: {parent}")
        except OSError as exc:
            raise InvalidInputError(
                f"Cannot create parent directory for file_path: {exc}"
            ) from exc
    return p


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------


def _safe_markdown_url(url: str) -> str:
    """Ensure the URL is safe for Markdown inline links.

    Percent-encodes parentheses and brackets to prevent Markdown breakage.

    Args:
        url: Original URL string.

    Returns:
        URL with special characters percent-encoded.
    """
    safe = url.replace("(", "%28").replace(")", "%29")
    safe = safe.replace("[", "%5B").replace("]", "%5D")
    return safe


def _format_markdown_source(source: SourceDict) -> str:
    """Format a single source as a Markdown list item.

    Args:
        source: Validated source dictionary (must contain 'title' and 'url').

    Returns:
        Markdown-formatted list item string.
    """
    title = source.get("title", "").strip()
    url = source.get("url", "").strip()
    safe_url = _safe_markdown_url(url)
    snippet = source.get("snippet", "")
    source_name = source.get("source_name", "")

    parts: list[str] = []
    parts.append(f"- [{title}]({safe_url})")
    if source_name:
        parts[-1] += f" (*{source_name}*)"
    if snippet:
        # Limit snippet length for readability
        truncated_snippet = snippet[:200] + "..." if len(snippet) > 200 else snippet
        parts.append(f"  > {truncated_snippet}")
    return "\n".join(parts)


def _format_html_source(source: SourceDict) -> str:
    """Format a single source as an HTML list item.

    Args:
        source: Validated source dictionary.

    Returns:
        HTML <li> element string with proper escaping.
    """
    title = html.escape(source.get("title", "").strip(), quote=True)
    url = html.escape(source.get("url", "").strip(), quote=True)
    snippet = source.get("snippet", "").strip()
    source_name = source.get("source_name", "").strip()

    item = f'<li><a href="{url}" rel="noopener noreferrer">{title}</a>'
    if source_name:
        item += f" <em>({html.escape(source_name)})</em>"
    if snippet:
        truncated = snippet[:200] + "..." if len(snippet) > 200 else snippet
        item += f"<br><blockquote>{html.escape(truncated)}</blockquote>"
    item += "</li>"
    return item


def _wrap_lines(text: str, max_length: int = _MAX_LINE_LENGTH) -> str:
    """Wrap text at word boundaries to a given maximum line length.

    Args:
        text: Input text to wrap.
        max_length: Maximum number of characters per line.

    Returns:
        Wrapped text with newlines inserted.
    """
    if max_length <= 0:
        return text

    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        current_line: list[str] = []
        current_len = 0
        for word in words:
            # Calculate length if adding this word
            space_len = 1 if current_line else 0
            if current_len + len(word) + space_len > max_length:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                    current_len = len(word)
                else:
                    # Single word too long, add anyway
                    lines.append(word)
                    current_len = 0
            else:
                if current_line:
                    current_len += 1  # space
                current_line.append(word)
                current_len += len(word)
        if current_line:
            lines.append(" ".join(current_line))
        else:
            lines.append("")  # preserve empty lines
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _build_markdown_content(
    report_date: date,
    executive_summary: str,
    sources: Sequence[SourceDict],
) -> str:
    """Build the complete Markdown content as a single string.

    Args:
        report_date: Date to display in header.
        executive_summary: Body of the executive summary.
        sources: Validated list of source dictionaries.

    Returns:
        Markdown formatted string.
    """
    parts: list[str] = []

    # --- Header ---
    parts.append(f"# 📰 Daily Content Summary – {report_date.isoformat()}")
    parts.append("")
    parts.append(f"**Generated:** {date.today().isoformat()}")
    parts.append("")

    # --- Executive Summary ---
    parts.append("## Executive Summary")
    parts.append("")
    wrapped_summary = _wrap_lines(executive_summary.strip(), max_length=_MAX_LINE_LENGTH)
    parts.append(wrapped_summary)
    parts.append("")

    # --- Sources ---
    parts.append("## Sources")
    parts.append("")
    if not sources:
        parts.append("*No sources available for this report.*")
    else:
        parts.append(f"*{len(sources)} sources listed.*")
        parts.append("")
        for src in sources:
            parts.append(_format_markdown_source(src))
            parts.append("")  # blank line between items

    # Trim trailing blank lines
    while parts and parts[-1] == "":
        parts.pop()
    parts.append("")  # final newline

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------


def _build_html_content(
    report_date: date,
    executive_summary: str,
    sources: Sequence[SourceDict],
) -> str:
    """Build the complete HTML content as a single string.

    Args:
        report_date: Date to display in header.
        executive_summary: Body of the executive summary.
        sources: Validated list of source dictionaries.

    Returns:
        HTML formatted string with proper escaping.
    """
    if not sources:
        sources_html = "<p><em>No sources available for this report.</em></p>"
    else:
        items = [_format_html_source(src) for src in sources]
        sources_html = (
            f"<p>{len(sources)} sources listed.</p>\n<ul>\n"
            + "\n".join(f"    {item}" for item in items)
            + "\n</ul>"
        )

    html_title = html.escape(f"Daily Content Summary – {report_date.isoformat()}", quote=True)
    safe_summary = html.escape(executive_summary.strip(), quote=True)
    escaped_summary = _wrap_lines(safe_summary, max_length=_MAX_LINE_LENGTH).replace("\n", "<br>\n")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="{_DEFAULT_ENCODING}">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html_title}</title>
    <style>
        body {{ font-family: Arial, Helvetica, sans-serif; line-height: 1.6; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
        h1 {{ color: #333; }}
        h2 {{ color: #555; }}
        ul {{ padding-left: 1.5rem; }}
        li {{ margin-bottom: 0.5rem; }}
        blockquote {{ margin-left: 0; padding-left: 1rem; border-left: 3px solid #ccc; color: #666; }}
        a {{ color: #0366d6; }}
        small {{ color: #777; }}
    </style>
</head>
<body>
    <h1>{html_title}</h1>
    <p><small>Generated: {html.escape(date.today().isoformat())}</small></p>

    <h2>Executive Summary</h2>
    <p>{escaped_summary}</p>

    <h2>Sources</h2>
    {sources_html}
</body>
</html>"""
    return html_content


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    report_date: date,
    executive_summary: str,
    sources: Sequence[SourceDict],
    output_format: OutputFormat = "markdown",
    file_path: Optional[Union[str, Path]] = None,
    max_line_length: int = _MAX_LINE_LENGTH,
) -> str:
    """Generate a formatted report (Markdown or HTML) with validation.

    Args:
        report_date: The date to associate with the report.
        executive_summary: Main summary text.
        sources: List of dictionaries with 'title' and 'url' (required),
            plus optional 'snippet' and 'source_name'.
        output_format: One of "markdown", "md", "html", "htm".
        file_path: Optional file path to write the output.
        max_line_length: Maximum line length for text wrapping (default 120).

    Returns:
        Formatted report as a string.

    Raises:
        InvalidInputError: If any input parameter fails validation.
        InvalidSourceError: If any source dictionary is malformed.
        OutputWriteError: If writing to file_path fails.

    Example:
        >>> from datetime import date
        >>> sources = [{"title": "Example", "url": "https://example.com"}]
        >>> report = generate_report(date(2026, 5, 29), "Summary.", sources)
        >>> print(report)  # Markdown text
    """
    logger.info(f"{_LOG_PREFIX} Starting report generation for date {report_date}")

    # --- Validate all inputs ---
    try:
        _validate_report_date(report_date)
        _validate_executive_summary(executive_summary)
        _validate_sources(sources)
        fmt = _validate_format(output_format)
        resolved_path = _validate_file_path(file_path)
    except (InvalidInputError, InvalidSourceError):
        logger.exception(f"{_LOG_PREFIX} Input validation failed")
        raise

    # --- Generate content ---
    try:
        if fmt == "html":
            content = _build_html_content(
                report_date=report_date,
                executive_summary=executive_summary,
                sources=sources,
            )
        else:
            content = _build_markdown_content(
                report_date=report_date,
                executive_summary=executive_summary,
                sources=sources,
            )
    except Exception as exc:
        logger.exception(f"{_LOG_PREFIX} Failed to build report content")
        raise ReportGenerationError(f"Content generation failed: {exc}") from exc

    logger.info(f"{_LOG_PREFIX} Report content generated ({len(content)} characters)")

    # --- Optionally write to file ---
    if resolved_path is not None:
        try:
            resolved_path.write_text(content, encoding=_DEFAULT_ENCODING)
            logger.info(f"{_LOG_PREFIX} Report written to {resolved_path}")
        except OSError as exc:
            logger.exception(f"{_LOG_PREFIX} Failed to write report to {resolved_path}")
            raise OutputWriteError(f"Cannot write to {resolved_path}: {exc}") from exc

    return content


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

__all__ = [
    "generate_report",
    "ReportGenerationError",
    "InvalidSourceError",
    "InvalidInputError",
    "OutputWriteError",
    "OutputFormat",
    "SourceDict",
]