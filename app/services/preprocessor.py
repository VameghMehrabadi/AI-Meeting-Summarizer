"""Text preprocessing: cleaning and chunking for summarization.

Provides:
- ``clean(text)``: normalize whitespace, drop filler lines, collapse repeated
  blank lines, and strip speaker labels into a consistent form.
- ``chunk(text)``: split a long transcript into overlapping sentence-based
  chunks sized to fit a summarizer's token window.
"""
import re
from typing import List

from app.core.config import CHUNK_TOKEN_TARGET, CHUNK_OVERLAP_SENTENCES

# Patterns
_FILLER_RE = re.compile(r"\b(um|uh|er|erm|like, you know|you know)\b", re.IGNORECASE)
_REPEATED_WS_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
# Speaker labels like "John:", "John Smith:", "J. Doe:", "Speaker 1:"
_SPEAKER_RE = re.compile(r"^\s*([A-Z][A-Za-z.''-]+(?:\s+[A-Z][A-Za-z.''-]+)?|Speaker\s+\d+)\s*:\s*")
_TIMESTAMP_RE = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")


def clean(text: str) -> str:
    """Normalize a raw transcript."""
    if not text:
        return ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            lines.append("")
            continue
        # Remove standalone timestamps
        line = _TIMESTAMP_RE.sub("", line).strip()
        if not line:
            continue
        # Keep speaker labels but normalize spacing
        m = _SPEAKER_RE.match(line)
        if m:
            speaker = m.group(1).strip()
            rest = line[m.end():].strip()
            line = f"{speaker}: {rest}" if rest else speaker
        # Remove filler words
        line = _FILLER_RE.sub("", line)
        line = _REPEATED_WS_RE.sub(" ", line).strip()
        lines.append(line)

    cleaned = "\n".join(lines)
    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned).strip()
    return cleaned


def _split_sentences(text: str) -> List[str]:
    """Lightweight sentence splitter (avoids extra deps)."""
    # Protect common abbreviations from being split on
    text = re.sub(r"\b(Mr|Mrs|Ms|Dr|Prof|Inc|Ltd|Corp|vs|e\.g|i\.e)\.", r"\1<DOT>", text)
    # Split on sentence enders followed by whitespace + capital
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    sentences = []
    for p in parts:
        p = p.replace("<DOT>", ".").strip()
        if p:
            sentences.append(p)
    return sentences


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


def chunk(text: str, target_tokens: int = CHUNK_TOKEN_TARGET, overlap_sentences: int = CHUNK_OVERLAP_SENTENCES) -> List[str]:
    """Split text into overlapping sentence-based chunks.

    Each chunk targets ``target_tokens`` tokens (rough char/4 estimate) and
    overlaps the previous chunk by ``overlap_sentences`` sentences so context
    is preserved across boundaries.
    """
    if not text:
        return []

    sentences = _split_sentences(text)
    if not sentences:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    current_tokens = 0
    i = 0

    while i < len(sentences):
        sent = sentences[i]
        sent_tokens = _estimate_tokens(sent)

        if current and current_tokens + sent_tokens > target_tokens and len(current) >= 2:
            chunks.append(" ".join(current))
            # Start new chunk with overlap
            overlap = current[-overlap_sentences:] if overlap_sentences else []
            current = list(overlap)
            current_tokens = sum(_estimate_tokens(s) for s in current)
        current.append(sent)
        current_tokens += sent_tokens
        i += 1

    if current:
        chunks.append(" ".join(current))

    # If a single sentence is huge, fall back to splitting by tokens
    final: List[str] = []
    for c in chunks:
        if _estimate_tokens(c) <= target_tokens * 1.2:
            final.append(c)
        else:
            # Hard split very long chunks by characters
            step = target_tokens * 4
            for j in range(0, len(c), step):
                final.append(c[j:j + step])
    return final
