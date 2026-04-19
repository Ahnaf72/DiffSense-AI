"""Text chunking module — split extracted text into embedding-ready chunks.

Supports paragraph-based and sentence-based splitting with overlap,
text cleaning, and sequential chunk IDs.

Usage:
    from app.core.chunker import chunk_text

    chunks = chunk_text(raw_text, strategy="paragraph", max_tokens=256)
    for c in chunks:
        print(c.chunk_index, c.content[:80])
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Rough token estimate: ~4 chars per token for English ─────────────
CHARS_PER_TOKEN = 4


# ── Structured output ────────────────────────────────────────────────


@dataclass
class TextChunk:
    """A single chunk ready for embedding and DB storage."""
    chunk_index: int
    content: str
    token_count: int
    char_count: int


# ── Text cleaning ────────────────────────────────────────────────────


def clean_text(text: str) -> str:
    """Normalize whitespace, strip control chars, fix common PDF artifacts."""
    # Normalize unicode
    text = unicodedata.normalize("NFKC", text)
    # Remove control characters except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse horizontal whitespace (multiple spaces/tabs → single space)
    text = re.sub(r"[ \t]+", " ", text)
    # Remove leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    # Collapse 3+ consecutive blank lines into 2 (paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    # Strip hyphenation at line breaks (common in PDFs)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    return text.strip()


# ── Splitting strategies ──────────────────────────────────────────────


def _split_paragraphs(text: str) -> list[str]:
    """Split on double-newline boundaries."""
    parts = re.split(r"\n\s*\n", text)
    return [p.strip() for p in parts if p.strip()]


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries (., !, ?) followed by whitespace or end."""
    # Handles common abbreviations poorly — good enough for chunking
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


# ── Token-aware merging ──────────────────────────────────────────────


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def _merge_small_units(
    units: list[str],
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    """Merge small text units into chunks that fit within max_tokens.

    Uses a sliding-window approach with overlap between consecutive chunks.
    """
    if not units:
        return []

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0

    for unit in units:
        unit_tokens = _estimate_tokens(unit)

        # If a single unit exceeds max_tokens, split it by characters
        if unit_tokens > max_tokens:
            # Flush current chunk first
            if current_parts:
                chunks.append(" ".join(current_parts))
                current_parts = []
                current_tokens = 0
            # Split the oversized unit
            max_chars = max_tokens * CHARS_PER_TOKEN
            for i in range(0, len(unit), max_chars):
                piece = unit[i : i + max_chars].strip()
                if piece:
                    chunks.append(piece)
            continue

        # Would this unit overflow the current chunk?
        if current_tokens + unit_tokens > max_tokens and current_parts:
            chunks.append(" ".join(current_parts))

            # Overlap: keep tail of current chunk for next chunk
            if overlap_tokens > 0:
                overlap_parts: list[str] = []
                overlap_count = 0
                for p in reversed(current_parts):
                    p_tokens = _estimate_tokens(p)
                    if overlap_count + p_tokens > overlap_tokens:
                        break
                    overlap_parts.insert(0, p)
                    overlap_count += p_tokens
                current_parts = overlap_parts
                current_tokens = overlap_count
            else:
                current_parts = []
                current_tokens = 0

        current_parts.append(unit)
        current_tokens += unit_tokens

    # Flush remaining
    if current_parts:
        chunks.append(" ".join(current_parts))

    return chunks


# ── Public API ───────────────────────────────────────────────────────


def chunk_text(
    text: str,
    *,
    strategy: str = "paragraph",
    max_tokens: int = 256,
    overlap_tokens: int = 32,
    min_chunk_tokens: int = 10,
) -> list[TextChunk]:
    """Split text into embedding-ready chunks.

    Args:
        text: Raw text (typically from PDF extraction).
        strategy: "paragraph" or "sentence".
        max_tokens: Maximum tokens per chunk (estimated).
        overlap_tokens: Overlap between consecutive chunks for context continuity.
        min_chunk_tokens: Discard chunks smaller than this.

    Returns:
        List of TextChunk with sequential chunk_index, cleaned content,
        and estimated token counts.
    """
    if not text or not text.strip():
        return []

    # Clean
    cleaned = clean_text(text)

    # Split into units
    if strategy == "sentence":
        units = _split_sentences(cleaned)
    else:
        units = _split_paragraphs(cleaned)

    if not units:
        return []

    # Merge into token-bounded chunks with overlap
    merged = _merge_small_units(units, max_tokens=max_tokens, overlap_tokens=overlap_tokens)

    # Build output
    chunks: list[TextChunk] = []
    for idx, content in enumerate(merged):
        token_count = _estimate_tokens(content)
        if token_count < min_chunk_tokens:
            continue
        chunks.append(TextChunk(
            chunk_index=idx,
            content=content,
            token_count=token_count,
            char_count=len(content),
        ))

    # Re-index after filtering
    for i, c in enumerate(chunks):
        c.chunk_index = i

    logger.info(
        "Chunked text: %d chars → %d chunks (strategy=%s, max_tokens=%d)",
        len(cleaned), len(chunks), strategy, max_tokens,
    )
    return chunks
