# AI Meeting Summarizer & Action Tracker

A web application that summarizes meetings and extracts action items automatically using local open-source deep-learning models. It accepts meeting **audio** (auto-transcribed via Whisper) or **text transcripts** and produces:

- A concise summary of key discussions
- A structured list of decisions and action items
- Deadline + responsible-person tracking (NER + rule-based)
- Speaker diarization (text-based detection from transcript)
- A clean, structured meeting report (PDF export)

**Languages**: English and Farsi (Persian), with automatic language detection.

## Stack
- **Backend**: Python + FastAPI
- **Frontend**: Single-page HTML/CSS/JS (`index.html`) — no build step, no external dependencies beyond Google Fonts
- **Transcription**: faster-whisper (local, multilingual)
- **Speaker detection**: Text-based diarization from transcript (detects speaker labels and name patterns)
- **Summarization**: HuggingFace transformers — `facebook/bart-large-cnn` (English) and `csebuetnlp/mT5_multilingual_XLSum` (Farsi)
- **Entity extraction**: spaCy NER (English) + HuggingFace Persian NER `HooshvareLab/bert-fa-zwnj-base-ner` (Farsi) + rule-based date parsing (`dateparser`, `jdatetime` for Jalali dates)
- **PDF reports**: reportlab with Tahoma font (Persian + English support)
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
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# 5. (Optional) Generate a sample English audio file for testing
python make_sample_audio.py

# 6. Run the app
python run.py
```

Then open <http://localhost:8000> in your browser.

## Usage
1. Open the web app — it auto-connects to the backend API.
2. Choose input mode: **Upload Audio** (`.mp3`, `.wav`, `.m4a`) or **Paste Transcript**.
3. Enter a meeting title (optional) and participants (optional).
4. Click **اجرای پردازش** (Run Processing). The pipeline runs:
   - Transcription (if audio) with speaker detection
   - Summarization
   - Action-item extraction (owner + deadline)
5. View results in three tabs: Summary, Actions & Deadlines, and Dialogue.
6. Click **ذخیره در آرشیو جلسات** to save the meeting to the database.
7. Click **دانلود گزارش PDF** to download a structured PDF report.

## API Endpoints
```
GET    /api/health              -> { ok: true }
POST   /api/transcribe          (multipart file)  -> { transcript, speakers, segments }
POST   /api/summarize           { transcript }    -> { summary }
POST   /api/extract-actions     { transcript }    -> { items: [{task, owner, deadline}] }
POST   /api/meetings            { title, transcript, summary, items, speakers, duration } -> { id }
GET    /api/meetings            -> { meetings: [{id, title, date, duration, status}] }
GET    /api/meetings/:id        -> full meeting object
GET    /api/meetings/:id/report -> PDF download
DELETE /api/meetings/:id       -> { ok: true }
```

## Language support
- **English**: spaCy NER + BART summarizer + English rule patterns.
- **Farsi**: ParsBERT NER + mT5 XLSum summarizer + Farsi rule patterns (باید/خواهد/تصمیم/مهلت/تا...) + Jalali (Shamsi) date conversion via `jdatetime`.
- Language is auto-detected from the transcript, or can be forced from the UI.

## Notes
- The first run downloads several GB of model weights (Whisper base, BART-large-cnn, and — only when Farsi is used — mT5 XLSum + ParsBERT NER). Subsequent runs use the cache.
- CPU inference works for short meetings; a GPU is recommended for long audio.
- Long transcripts are summarized via map-reduce chunking so the model context window is never exceeded.
- Farsi NER and summarizer models are loaded lazily — they only download when a Farsi transcript is processed.
- `starlette<0.42.0` is pinned in requirements.txt for FastAPI 0.115.x compatibility.

## Testing
```bash
python tests/test_pipeline.py
```

## Project Structure
```
index.html            Single-page frontend (SPA)
app/                 FastAPI application
  app/api/            REST endpoints (meetings, reports, pipeline)
  app/core/           Config, models, language detection
  app/services/       Transcriber, summarizer, extractor, preprocessor
  app/db/             Database (SQLAlchemy)
  app/templates/      Legacy Jinja2 templates (meetings list, report view)
static/               CSS and JS for legacy templates
uploads/              Uploaded audio files (gitignored)
data/                 SQLite database (gitignored)
tests/                Test scripts and sample files
run.py                Uvicorn launcher
make_sample_audio.py  Generate sample English audio via TTS
```
