"""Language detection and language-aware utilities.

Detects the dominant script of a transcript to decide between English and
Farsi processing. Detection is script-based (Persian/Arabic Unicode block)
which is fast, dependency-free, and reliable for our two-language case.
"""
import re
from typing import Literal

Lang = Literal["en", "fa"]

# Persian/Arabic script range (covers Persian, Arabic letters + Persian digits)
_PERSIAN_SCRIPT_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")


def detect_language(text: str) -> Lang:
    """Return ``"fa"`` if the text is mostly Persian script, else ``"en"``.

    Uses a simple ratio of Persian-script characters vs Latin characters so a
    few English names inside a Farsi transcript do not flip the detection.
    """
    if not text:
        return "en"
    persian_chars = len(_PERSIAN_SCRIPT_RE.findall(text))
    latin_chars = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    if persian_chars == 0:
        return "en"
    # If Persian script dominates (or is comparable to Latin), treat as Farsi
    return "fa" if persian_chars >= latin_chars * 0.5 else "en"


def resolve_language(requested: str, text: str) -> Lang:
    """Resolve a user-requested language hint against auto-detection.

    ``requested`` is one of ``"auto"``, ``"en"``, ``"fa"``. When ``"auto"``,
    the language is detected from ``text``.
    """
    if requested == "en":
        return "en"
    if requested == "fa":
        return "fa"
    return detect_language(text)
