# AI Meeting Summarizer & Action Tracker

A web application that summarizes meetings and extracts action items automatically using local open-source deep-learning models. It accepts meeting **audio** (auto-transcribed via Whisper) or **text transcripts** and produces:

- A concise summary of key discussions
- A structured list of decisions and action items
- Deadline + responsible-person tracking (NER + rule-based)
- A clean, structured meeting report

**Languages**: English and Farsi (Persian), with automatic language detection.

## Stack
- **Backend**: Python + FastAPI
- **Frontend**: Vanilla HTML/CSS/JS (Jinja2 templates)
- **Transcription**: faster-whisper (local, multilingual)
- **Summarization**: HuggingFace transformers — `facebook/bart-large-cnn` (English) and `csebuetnlp/mT5_multilingual_XLSum` (Farsi)
- **Entity extraction**: spaCy NER (English) + HuggingFace Persian NER `HooshvareLab/bert-fa-zwnj-base-ner` (Farsi) + rule-based date parsing (`dateparser`, `jdatetime` for Jalali dates)
- **Storage**: SQLite via SQLAlchemy

All models run locally — no API keys, works offline after the first model download.

## Setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 2. Upgrade pip (recommended on older installs)
python -m pip install --upgrade pip

# 3. Install dependencies
pip install -r requirements.txt

# 4. Download the spaCy English model
python -m spacy download en_core_web_sm

# 5. Pre-download model weights (one-time, ~1.7 GB for English; +~720 MB if --all for Farsi)
python download_models.py            # English only
# or, to also pre-download the Farsi models:
# python download_models.py --all

# 6. Run the app (loads models from local cache only — no network downloads)
python run.py
```

Then open <http://localhost:8000> in your browser.

## Usage
1. Open the web app.
2. Pick a **language** (Auto-detect, English, or فارسی).
3. Either **upload an audio file** (`.mp3`, `.wav`, `.m4a`) — it will be transcribed automatically — or **paste a meeting transcript** into the text box.
4. Click **Process**. The pipeline runs transcription (if audio), summarization, and action-item extraction.
5. View the structured report: summary, decisions, action items (with owner + deadline), and participants.
6. Export the report as JSON or Markdown.

## Language support
- **English**: spaCy NER + BART summarizer + English rule patterns.
- **Farsi**: ParsBERT NER + mT5 XLSum summarizer + Farsi rule patterns (باید/خواهد/تصمیم/مهلت/تا...) + Jalali (Shamsi) date conversion via `jdatetime`.
- Language is auto-detected from the transcript script, or can be forced from the UI dropdown. For audio, the chosen language hint is passed to Whisper.

## Notes
- The first run downloads several GB of model weights (Whisper base, BART-large-cnn, and — only when Farsi is used — mT5 XLSum + ParsBERT NER). Subsequent runs use the cache.
- CPU inference works for short meetings; a GPU is recommended for long audio.
- Long transcripts are summarized via map-reduce chunking so the model context window is never exceeded.
- Farsi NER and summarizer models are loaded lazily — they only download when a Farsi transcript is processed.

## Testing
A lightweight test exercises the pipeline on English and Farsi samples without downloading the heavy summarizer (it is stubbed):
```bash
python tests/test_pipeline.py
```
The Farsi extraction step requires `transformers` + `torch` (for the ParsBERT NER); it is skipped gracefully if unavailable.

## Project Structure
```
app/                 FastAPI application (api, core, services, db, templates)
static/              CSS and JS
uploads/             Uploaded audio files
data/                SQLite database
tests/               Pipeline test scripts
run.py               Uvicorn launcher
```
