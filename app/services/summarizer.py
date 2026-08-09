"""Abstractive summarization using local HuggingFace models.

Language-aware:
- English  -> ``facebook/bart-large-cnn``
- Farsi     -> ``csebuetnlp/mT5_multilingual_XLSum``

Both use a map-reduce strategy for long transcripts: summarize each chunk
independently, then summarize the concatenated chunk summaries to produce a
single coherent abstract.

Models and tokenizers are loaded lazily and cached per language.
"""
import logging
from typing import List, Optional

from app.core.config import (
    SUMMARIZER_EN_MODEL_NAME,
    SUMMARIZER_FA_MODEL_NAME,
    SUMMARY_MAX_LENGTH,
    SUMMARY_MIN_LENGTH,
)

logger = logging.getLogger(__name__)

# Per-language caches: {"en": (tokenizer, model), "fa": (tokenizer, model)}
_cache = {}


def _load(lang: str):
    if lang not in _cache:
        from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
        name = SUMMARIZER_EN_MODEL_NAME if lang == "en" else SUMMARIZER_FA_MODEL_NAME
        logger.info("Loading summarizer model '%s' (lang=%s)...", name, lang)
        tokenizer = AutoTokenizer.from_pretrained(name)
        model = AutoModelForSeq2SeqLM.from_pretrained(name)
        _cache[lang] = (tokenizer, model)
        logger.info("Summarizer model '%s' loaded.", name)
    return _cache[lang]


def _summarize_text(text: str, lang: str, max_length: int, min_length: int) -> str:
    """Summarize a single piece of text with the model for ``lang``."""
    if not text.strip():
        return ""
    tokenizer, model = _load(lang)

    # XLSum (mT5) expects a "summarize: " prefix; BART does not.
    if lang == "fa":
        text = ("summarize: " + text) if not text.lower().startswith("summarize") else text

    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=1024)
    summary_ids = model.generate(
        **inputs,
        max_length=max_length,
        min_length=min_length,
        num_beams=4,
        length_penalty=2.0,
        early_stopping=True,
    )
    return tokenizer.decode(summary_ids[0], skip_special_tokens=True).strip()


def summarize(chunks: List[str], lang: str = "en", max_length: int = SUMMARY_MAX_LENGTH, min_length: int = SUMMARY_MIN_LENGTH) -> str:
    """Summarize a list of transcript chunks using map-reduce.

    Args:
        chunks: Pre-chunked transcript pieces (from ``preprocessor.chunk``).
        lang: ``"en"`` or ``"fa"``.

    Returns:
        A single summary string.
    """
    if not chunks:
        return ""
    if len(chunks) == 1:
        return _summarize_text(chunks[0], lang=lang, max_length=max_length, min_length=min_length)

    logger.info("Summarizing %d chunks (map-reduce, lang=%s)...", len(chunks), lang)

    # Map: summarize each chunk
    chunk_summaries: List[str] = []
    per_chunk_max = max(80, max_length // 2)
    per_chunk_min = max(20, min_length // 2)
    for i, c in enumerate(chunks):
        try:
            s = _summarize_text(c, lang=lang, max_length=per_chunk_max, min_length=per_chunk_min)
            if s:
                chunk_summaries.append(s)
        except Exception as e:
            logger.warning("Chunk %d summarization failed: %s", i, e)

    if not chunk_summaries:
        return ""

    # Reduce: combine chunk summaries and summarize once more
    combined = " ".join(chunk_summaries)
    if len(combined.split()) <= max_length:
        return combined

    return _summarize_text(combined, lang=lang, max_length=max_length, min_length=min_length)


def highlights(chunks: List[str], top_k: int = 5) -> List[str]:
    """Optional: extract a few highlight sentences (cue-word heuristic)."""
    import re as _re
    cue = _re.compile(
        r"\b(decide|decision|action|deadline|must|will|should|by|owner|responsible|approve|approved)\b"
        r"|(?:تصمیم|اقدام|مهلت|باید|خواهد|مسئول)",
        _re.IGNORECASE,
    )
    all_sents: List[str] = []
    for c in chunks:
        all_sents.extend(_re.split(r"(?<=[.!?؟])\s+", c))
    scored = [(len(s.split()) + (5 if cue.search(s) else 0), s.strip()) for s in all_sents if 5 < len(s.split()) < 60]
    scored.sort(reverse=True)
    seen = set()
    out = []
    for _, s in scored:
        if s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(s)
        if len(out) >= top_k:
            break
    return out
