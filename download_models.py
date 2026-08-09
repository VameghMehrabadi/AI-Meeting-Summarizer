"""Pre-download all model weights to the local cache.

Run this ONCE before starting the API. After it finishes, ``python run.py``
will only load models from the local cache into RAM (no network downloads
during request processing).

Usage:
    python download_models.py            # English models only
    python download_models.py --all       # English + Farsi models
    python download_models.py --fa        # Farsi models only

Models downloaded:
- faster-whisper "base"               (audio transcription, ~140 MB)
- facebook/bart-large-cnn              (English summarizer, ~1.5 GB)
- csebuetnlp/mT5_multilingual_XLSum    (Farsi summarizer, ~600 MB)   [--all/--fa]
- HooshvareLab/bert-fa-zwnj-base-ner   (Farsi NER, ~120 MB)          [--all/--fa]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.core.config import (
    WHISPER_MODEL_NAME,
    SUMMARIZER_EN_MODEL_NAME,
    SUMMARIZER_FA_MODEL_NAME,
    NER_FA_MODEL_NAME,
)


def _download_whisper():
    print(f"[1/4] Downloading faster-whisper model '{WHISPER_MODEL_NAME}'...")
    from faster_whisper import WhisperModel
    WhisperModel(WHISPER_MODEL_NAME, device="cpu", compute_type="int8")
    print("  done.")


def _download_summarizer_en():
    print(f"[2/4] Downloading English summarizer '{SUMMARIZER_EN_MODEL_NAME}'...")
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    AutoTokenizer.from_pretrained(SUMMARIZER_EN_MODEL_NAME)
    AutoModelForSeq2SeqLM.from_pretrained(SUMMARIZER_EN_MODEL_NAME)
    print("  done.")


def _download_summarizer_fa():
    print(f"[3/4] Downloading Farsi summarizer '{SUMMARIZER_FA_MODEL_NAME}'...")
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    AutoTokenizer.from_pretrained(SUMMARIZER_FA_MODEL_NAME)
    AutoModelForSeq2SeqLM.from_pretrained(SUMMARIZER_FA_MODEL_NAME)
    print("  done.")


def _download_ner_fa():
    print(f"[4/4] Downloading Farsi NER '{NER_FA_MODEL_NAME}'...")
    from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline
    AutoTokenizer.from_pretrained(NER_FA_MODEL_NAME)
    AutoModelForTokenClassification.from_pretrained(NER_FA_MODEL_NAME)
    # Warm up the pipeline so all weights are cached
    pipeline("ner", model=NER_FA_MODEL_NAME, tokenizer=NER_FA_MODEL_NAME, aggregation_strategy="simple")
    print("  done.")


def main():
    parser = argparse.ArgumentParser(description="Pre-download model weights.")
    parser.add_argument("--all", action="store_true", help="Download English + Farsi models")
    parser.add_argument("--fa", action="store_true", help="Download Farsi models only")
    args = parser.parse_args()

    include_fa = args.all or args.fa
    include_en = not args.fa  # default (no flags) => English only; --fa => Farsi only; --all => both

    print("This will download model weights to the local HuggingFace / faster-whisper cache.")
    print("One-time operation. Subsequent API runs load from cache only.\n")

    try:
        if include_en:
            _download_whisper()
            _download_summarizer_en()
        if include_fa:
            _download_summarizer_fa()
            _download_ner_fa()
    except Exception as e:
        print(f"\nERROR during download: {e}", file=sys.stderr)
        sys.exit(1)

    print("\nAll requested models downloaded successfully.")
    print("You can now run:  python run.py   (it will only load from cache, no downloads).")


if __name__ == "__main__":
    main()
