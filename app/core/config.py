"""Application configuration."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "meetings.db"

# Model choices
WHISPER_MODEL_NAME = "base"

# English summarizer (abstractive, CNN/DailyMail fine-tuned)
SUMMARIZER_EN_MODEL_NAME = "facebook/bart-large-cnn"
# Farsi/multilingual summarizer (mT5 fine-tuned on XLSum, supports Persian)
SUMMARIZER_FA_MODEL_NAME = "csebuetnlp/mT5_multilingual_XLSum"

# Persian NER model (ParsBERT-based, lightweight)
NER_FA_MODEL_NAME = "HooshvareLab/bert-fa-zwnj-base-ner"

# Default summarizer (kept for backwards-compat imports)
SUMMARIZER_MODEL_NAME = SUMMARIZER_EN_MODEL_NAME

# Summarization parameters
SUMMARY_MAX_LENGTH = 150
SUMMARY_MIN_LENGTH = 40
CHUNK_TOKEN_TARGET = 900      # tokens per chunk (BART max is 1024)
CHUNK_OVERLAP_SENTENCES = 2

# Upload constraints
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".webm", ".ogg"}
MAX_AUDIO_SIZE_MB = 500

# Supported languages
SUPPORTED_LANGUAGES = {"auto": "Auto-detect", "en": "English", "fa": "فارسی"}

# Ensure directories exist
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
