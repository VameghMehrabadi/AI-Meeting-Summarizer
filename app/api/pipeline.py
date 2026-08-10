"""Pipeline endpoints for the single-page frontend (index.html).

These endpoints expose the speech/NLP pipeline directly so the frontend can
run transcription, summarization, and action-extraction as separate steps
and then persist a fully-assembled meeting in one request.
"""
import logging
import re
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel

from app.core.config import ALLOWED_AUDIO_EXTENSIONS
from app.core.language import resolve_language
from app.services import preprocessor, summarizer, extractor, transcriber

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["pipeline"])

# Speaker color palette
SPEAKER_COLORS = [
    "#e4a33f",  # amber
    "#6fbfa5",  # teal
    "#e2664a",  # red
    "#7b8cf0",  # blue
    "#c47fd6",  # purple
    "#f0c060",  # gold
    "#5ec4d6",  # cyan
    "#d67ba0",  # pink
]


class TranscriptIn(BaseModel):
    transcript: str


# ---------- Health ----------
@router.get("/health")
def health():
    return {"ok": True}


# ---------- Transcribe ----------
@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    if not file.filename or Path(file.filename).suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        return {"error": "Unsupported file type"}

    contents = await file.read()
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        segs = transcriber.transcribe_with_segments(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    text = " ".join(s["text"] for s in segs)
    speakers, segments = _diarize(text, segs)
    return {"transcript": text, "speakers": speakers, "segments": segments}


def _diarize(text: str, whisper_segments: list) -> tuple:
    """Detect speakers from transcript text and build display segments.

    Strategy:
    1. Look for explicit speaker labels: "Name:" or "Name," at sentence starts
    2. If none found, try detecting person names at the start of sentences
    3. Fallback: single speaker
    """
    if not text:
        return [], []

    # Pattern 1: "Name:" at start of a line (explicit speaker labels)
    colon_re = re.compile(
        r"([A-Z][A-Za-z.''-]+(?:\s+[A-Z][A-Za-z.''-]+)?)\s*:\s*",
    )
    # Pattern 2: "Name," at start of a sentence (TTS-style speaker markers)
    name_comma_re = re.compile(
        r"(?:^|\.\s+)([A-Z][a-z]+)\s*,\s+",
    )

    # Try pattern 1 first (explicit labels)
    if colon_re.search(text):
        return _split_by_colon(text)

    # Try pattern 2 (name + comma at sentence start)
    matches = list(name_comma_re.finditer(text))
    if len(matches) >= 2:
        return _split_by_name_comma(text, matches)

    # Fallback: single speaker, split by sentences
    return _split_single_speaker(text, whisper_segments)


def _split_by_colon(text: str) -> tuple:
    """Split text by explicit 'Name:' speaker labels."""
    pattern = re.compile(
        r"([A-Z][A-Za-z.''-]+(?:\s+[A-Z][A-Za-z.''-]+)?)\s*:\s*",
    )
    parts = pattern.split(text)
    # parts = ['', 'Speaker1', 'text...', 'Speaker2', 'text...', ...]
    speakers_map = {}
    segments = []
    idx = 1
    while idx < len(parts) - 1:
        name = parts[idx].strip()
        chunk = parts[idx + 1].strip()
        if name not in speakers_map:
            sid = f"s{len(speakers_map) + 1}"
            color = SPEAKER_COLORS[len(speakers_map) % len(SPEAKER_COLORS)]
            speakers_map[name] = {"id": sid, "name": name, "color": color}
        if chunk:
            segments.append({
                "speaker": name,
                "text": chunk,
                "start": 0,
                "end": 0,
            })
        idx += 2

    speakers = list(speakers_map.values())
    return speakers, segments


def _split_by_name_comma(text: str, matches: list) -> tuple:
    """Split text by 'Name,' patterns at sentence boundaries."""
    # Extract unique speaker names in order of appearance
    names_seen = []
    for m in matches:
        name = m.group(1)
        if name not in names_seen:
            names_seen.append(name)

    # Build speakers list
    speakers_map = {}
    for i, name in enumerate(names_seen):
        sid = f"s{i + 1}"
        color = SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
        speakers_map[name] = {"id": sid, "name": name, "color": color}

    # Build segments: split text at each "Name," occurrence
    segments = []
    # Find all positions where "Name," appears
    split_positions = []
    for m in matches:
        # The name starts after the period+space, or at position 0
        name_start = m.start(1)
        # The actual content starts after "Name, "
        content_start = m.end()
        split_positions.append((name_start, m.group(1), content_start))

    # Add end position
    for i, (name_start, name, content_start) in enumerate(split_positions):
        if i + 1 < len(split_positions):
            content_end = split_positions[i + 1][0]
        else:
            content_end = len(text)
        chunk = text[content_start:content_end].strip().rstrip(".")
        if chunk:
            chunk = chunk + "." if not chunk.endswith(".") else chunk
            segments.append({
                "speaker": name,
                "text": chunk,
                "start": 0,
                "end": 0,
            })

    # Handle text before the first speaker match
    if split_positions and split_positions[0][0] > 0:
        prefix = text[:split_positions[0][0]].strip()
        if prefix:
            segments.insert(0, {
                "speaker": names_seen[0] if names_seen else "گوینده ۱",
                "text": prefix,
                "start": 0,
                "end": 0,
            })

    speakers = list(speakers_map.values())
    return speakers, segments


def _split_single_speaker(text: str, whisper_segments: list) -> tuple:
    """Fallback: single speaker, split by whisper segments or sentences."""
    speaker = {"id": "s1", "name": "گوینده ۱", "color": SPEAKER_COLORS[0]}
    speakers = [speaker]

    if whisper_segments:
        segments = [
            {
                "speaker": "گوینده ۱",
                "text": s["text"],
                "start": s["start"],
                "end": s["end"],
            }
            for s in whisper_segments
            if s["text"]
        ]
    else:
        sentences = re.split(r"(?<=[.!?؟])\s+", text)
        segments = [
            {"speaker": "گوینده ۱", "text": s.strip(), "start": 0, "end": 0}
            for s in sentences
            if s.strip()
        ]

    return speakers, segments


# ---------- Summarize ----------
@router.post("/summarize")
def summarize(payload: TranscriptIn):
    text = payload.transcript or ""
    if not text.strip():
        return {"summary": ""}
    clean = preprocessor.clean(text)
    chunks = preprocessor.chunk(clean)
    lang = resolve_language("auto", clean)
    try:
        summary = summarizer.summarize(chunks, lang=lang)
    except Exception as e:
        logger.warning("Summarize failed: %s", e)
        summary = ""
    return {"summary": summary}


# ---------- Extract actions ----------
@router.post("/extract-actions")
def extract_actions(payload: TranscriptIn):
    text = payload.transcript or ""
    if not text.strip():
        return {"items": []}
    clean = preprocessor.clean(text)
    lang = resolve_language("auto", clean)
    try:
        extracted = extractor.extract(clean, lang=lang)
    except Exception as e:
        logger.warning("Extract actions failed: %s", e)
        extracted = {"action_items": [], "decisions": [], "participants": []}

    items = [
        {
            "task": a.get("text", ""),
            "owner": a.get("owner"),
            "deadline": a.get("due_date"),
        }
        for a in extracted.get("action_items", [])
    ]
    return {"items": items}
