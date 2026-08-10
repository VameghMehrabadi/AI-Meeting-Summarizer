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
    """Return a downloadable PDF report for the meeting."""
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")

    pdf_bytes = _build_pdf(m)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}-report.pdf"'},
    )


def _build_pdf(m) -> bytes:
    """Generate a PDF report from a meeting using reportlab."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT

    # Register Tahoma font (supports Persian + English)
    font_name = "Helvetica"
    try:
        pdfmetrics.registerFont(TTFont("Tahoma", "C:/Windows/Fonts/tahoma.ttf"))
        font_name = "Tahoma"
    except Exception:
        pass

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName=font_name,
                        fontSize=18, spaceAfter=12, textColor=colors.HexColor("#1a2133"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName=font_name,
                        fontSize=14, spaceAfter=8, spaceBefore=14, textColor=colors.HexColor("#2a3249"))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontName=font_name,
                          fontSize=11, leading=18, spaceAfter=6)
    meta = ParagraphStyle("Meta", parent=styles["Normal"], fontName=font_name,
                           fontSize=9, textColor=colors.grey, spaceAfter=14)

    story = []
    title = m.title or "Untitled Meeting"
    story.append(Paragraph(title, h1))
    created = m.created_at.isoformat() if m.created_at else "—"
    story.append(Paragraph(f"Source: {m.source_type} · Language: {m.language or '—'} · Created: {created}", meta))

    # Summary
    story.append(Paragraph("Summary", h2))
    story.append(Paragraph(m.summary or "No summary available.", body))
    story.append(Spacer(1, 10))

    # Action Items
    story.append(Paragraph("Action Items", h2))
    if m.action_items:
        data = [["Task", "Owner", "Due Date", "Status"]]
        for a in m.action_items:
            data.append([
                Paragraph(a.text or "", body),
                Paragraph(a.owner or "—", body),
                Paragraph(a.due_date or "—", body),
                Paragraph(a.status or "open", body),
            ])
        tbl = Table(data, colWidths=[7 * cm, 3 * cm, 3 * cm, 2.5 * cm])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a2133")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph("No action items detected.", body))
    story.append(Spacer(1, 10))

    # Decisions
    if m.decisions:
        story.append(Paragraph("Key Decisions", h2))
        for d in m.decisions:
            story.append(Paragraph(f"• {d.text}", body))
        story.append(Spacer(1, 10))

    # Participants
    story.append(Paragraph("Participants", h2))
    story.append(Paragraph(", ".join(m.participants or []) or "None detected.", body))
    story.append(Spacer(1, 10))

    # Transcript
    story.append(Paragraph("Transcript", h2))
    transcript_text = m.transcript or ""
    # Split long transcript into chunks to avoid layout issues
    for chunk in [transcript_text[i:i+500] for i in range(0, len(transcript_text), 500)]:
        story.append(Paragraph(chunk.replace("\n", "<br/>"), body))

    doc.build(story)
    return buf.getvalue()


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
