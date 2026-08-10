"""Audio transcription service using faster-whisper (CTranslate2 backend).

faster-whisper ships prebuilt wheels (no build step) and runs efficiently on
CPU. The model is loaded lazily and cached after first use.
"""
import logging
from pathlib import Path

from app.core.config import WHISPER_MODEL_NAME

logger = logging.getLogger(__name__)

_model = None  # cached WhisperModel


def _get_model():
    """Lazily load the faster-whisper model."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading faster-whisper model '%s'...", WHISPER_MODEL_NAME)
        # int8 on CPU is fast and small; falls back gracefully on most CPUs.
        _model = WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
        logger.info("Whisper model loaded.")
    return _model


def transcribe(audio_path: str, language: str = None) -> str:
    """Transcribe an audio file to text.

    Args:
        audio_path: Path to an audio file (.mp3, .wav, .m4a, ...).
        language: Optional language code (e.g. ``"en"``, ``"fa"``). When
            ``None``, faster-whisper auto-detects the spoken language.

    Returns:
        The recognized transcript as a single string.
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _get_model()
    segments, _info = model.transcribe(str(path), beam_size=5, language=language)
    text = " ".join(seg.text.strip() for seg in segments).strip()
    return text


def transcribe_with_segments(audio_path: str, language: str = None) -> list:
    """Transcribe an audio file and return segment-level info with timestamps.

    Returns:
        A list of dicts: ``[{"text", "start", "end"}, ...]``
    """
    path = Path(audio_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    model = _get_model()
    segments, _info = model.transcribe(str(path), beam_size=5, language=language)
    result = []
    for seg in segments:
        result.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 2),
            "end": round(seg.end, 2),
        })
    return result


def is_audio_filename(filename: str) -> bool:
    """Check whether a filename has an accepted audio extension."""
    from app.core.config import ALLOWED_AUDIO_EXTENSIONS
    return Path(filename).suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
