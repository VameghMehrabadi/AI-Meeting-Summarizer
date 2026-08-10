"""Meeting upload, list, get, status, and delete routes."""
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR, ALLOWED_AUDIO_EXTENSIONS, MAX_AUDIO_SIZE_MB, SUPPORTED_LANGUAGES
from app.core.language import resolve_language
from app.db.database import get_db
from app.db import crud
from app.core.models import Meeting, ActionItem, Decision

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meetings", tags=["meetings"])


# ---------- Schemas ----------
class MeetingOut(BaseModel):
    id: int
    title: Optional[str]
    source_type: str
    transcript: Optional[str]
    summary: Optional[str]
    participants: Optional[List[str]]
    status: str
    error: Optional[str]
    created_at: str
    action_items: List[dict] = []
    decisions: List[dict] = []

    class Config:
        from_attributes = True


class MeetingSaveIn(BaseModel):
    """JSON body for saving a fully-assembled meeting from the SPA frontend."""
    title: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    items: List[dict] = []
    speakers: Optional[List] = None
    duration: Optional[float] = 0


# ---------- Helpers ----------
def _serialize(m: Meeting) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "source_type": m.source_type,
        "language": m.language,
        "transcript": m.transcript,
        "summary": m.summary,
        "participants": m.participants or [],
        "status": m.status,
        "error": m.error,
        "created_at": m.created_at.isoformat() if m.created_at else None,
        "action_items": [
            {"id": a.id, "text": a.text, "owner": a.owner, "due_date": a.due_date, "status": a.status}
            for a in m.action_items
        ],
        "decisions": [{"id": d.id, "text": d.text} for d in m.decisions],
    }


# ---------- Routes ----------
@router.post("/upload-audio")
async def upload_audio(
    background_tasks: BackgroundTasks,
    title: Optional[str] = Form(None),
    language: str = Form("auto"),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if not audio.filename or Path(audio.filename).suffix.lower() not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use one of: " + ", ".join(sorted(ALLOWED_AUDIO_EXTENSIONS)))
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Use one of: {', '.join(SUPPORTED_LANGUAGES)}")

    contents = await audio.read()
    if len(contents) > MAX_AUDIO_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {MAX_AUDIO_SIZE_MB} MB).")

    save_path = UPLOAD_DIR / f"meeting_{audio.filename}"
    with open(save_path, "wb") as f:
        f.write(contents)

    meeting = crud.create_meeting(db, title=title, source_type="audio", audio_path=str(save_path), status="transcribing")
    background_tasks.add_task(_process_meeting, meeting.id, language)
    return {"meeting_id": meeting.id}


@router.post("/upload-text")
async def upload_text(
    background_tasks: BackgroundTasks,
    title: Optional[str] = Form(None),
    language: str = Form("auto"),
    transcript: str = Form(...),
    db: Session = Depends(get_db),
):
    if not transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript is empty.")
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language. Use one of: {', '.join(SUPPORTED_LANGUAGES)}")
    meeting = crud.create_meeting(db, title=title, source_type="text", transcript=transcript.strip(), status="preprocessing")
    background_tasks.add_task(_process_meeting, meeting.id, language)
    return {"meeting_id": meeting.id}


@router.get("")
def list_meetings(db: Session = Depends(get_db)):
    meetings = crud.list_meetings(db)
    return {
        "meetings": [
            {
                "id": m.id,
                "title": m.title,
                "source_type": m.source_type,
                "language": m.language,
                "status": m.status,
                "date": m.created_at.isoformat() if m.created_at else None,
                "duration": "—",
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in meetings
        ]
    }


@router.post("")
def save_meeting_from_json(payload: MeetingSaveIn, db: Session = Depends(get_db)):
    """Save a fully-assembled meeting (transcript + summary + items) from the SPA."""
    meeting = crud.create_meeting(
        db,
        title=payload.title,
        source_type="text",
        transcript=payload.transcript,
        status="done",
    )
    meeting.summary = payload.summary
    # Persist action items
    for it in payload.items:
        db.add(ActionItem(
            meeting_id=meeting.id,
            text=it.get("task") or it.get("text", ""),
            owner=it.get("owner"),
            due_date=it.get("deadline") or it.get("due_date"),
            status="open",
        ))
    # Persist participants
    if payload.speakers:
        participants = []
        for s in payload.speakers:
            if isinstance(s, dict):
                participants.append(s.get("name", ""))
            elif isinstance(s, str):
                participants.append(s)
        meeting.participants = [p for p in participants if p]
    db.commit()
    db.refresh(meeting)
    return {"id": meeting.id}


@router.get("/{meeting_id}")
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return _serialize(m)


@router.get("/{meeting_id}/status")
def meeting_status(meeting_id: int, db: Session = Depends(get_db)):
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return {"status": m.status, "error": m.error}


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    crud.delete_meeting(db, m)
    return {"ok": True}


@router.get("/{meeting_id}/report")
def meeting_report(meeting_id: int, db: Session = Depends(get_db)):
    """Return a downloadable report for the meeting.

    Generates a Markdown report served as a file download. The SPA frontend
    downloads it as meeting-report.pdf; for a true PDF, install reportlab/weasyprint.
    """
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")

    lines = [
        f"# {m.title or 'Untitled Meeting'}",
        "",
        f"*Source: {m.source_type} · Language: {m.language or '—'} · Created: {m.created_at.isoformat() if m.created_at else '—'}*",
        "",
        "## Summary",
        m.summary or "",
        "",
        "## Action Items",
    ]
    for a in m.action_items:
        lines.append(f"- {a.text} (owner: {a.owner or '—'}, due: {a.due_date or '—'})")
    lines += ["", "## Participants", ", ".join(m.participants or [])]
    lines += ["", "## Transcript", m.transcript or ""]
    content = "\n".join(lines)

    return Response(
        content=content,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}-report.md"'},
    )


# ---------- Background pipeline ----------
def _process_meeting(meeting_id: int, requested_lang: str = "auto") -> None:
    """Run the full processing pipeline for a meeting in a background thread."""
    from app.db.database import SessionLocal
    from app.services import preprocessor, summarizer, extractor, report_builder

    db = SessionLocal()
    try:
        meeting = crud.get_meeting(db, meeting_id)
        if not meeting:
            logger.warning("Meeting %s not found", meeting_id)
            return

        try:
            # 1. Transcription (audio only)
            if meeting.source_type == "audio" and meeting.audio_path:
                crud.update_meeting(db, meeting, status="transcribing")
                from app.services import transcriber
                whisper_lang = None if requested_lang == "auto" else requested_lang
                meeting.transcript = transcriber.transcribe(meeting.audio_path, language=whisper_lang)
                db.commit()

            # 2. Preprocessing
            crud.update_meeting(db, meeting, status="preprocessing")
            clean_text = preprocessor.clean(meeting.transcript or "")
            chunks = preprocessor.chunk(clean_text)

            # Resolve language (auto-detect from transcript unless forced)
            lang = resolve_language(requested_lang, clean_text)
            meeting.language = lang
            db.commit()
            logger.info("Meeting %s language resolved to '%s'", meeting_id, lang)

            # 3. Summarization
            crud.update_meeting(db, meeting, status="summarizing")
            summary = summarizer.summarize(chunks, lang=lang)
            meeting.summary = summary
            db.commit()

            # 4. Action / decision / entity extraction
            crud.update_meeting(db, meeting, status="extracting")
            extracted = extractor.extract(clean_text, lang=lang)

            # 5. Build & persist structured report
            crud.update_meeting(db, meeting, status="building")
            report_builder.build(db, meeting, extracted)

            crud.update_meeting(db, meeting, status="done")
        except Exception as e:
            logger.exception("Pipeline failed for meeting %s", meeting_id)
            crud.update_meeting(db, meeting, status="error", error=str(e))
    finally:
        db.close()
