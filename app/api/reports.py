"""Report export routes (JSON + Markdown downloads)."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db import crud

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _serialize(db, meeting) -> dict:
    return {
        "id": meeting.id,
        "title": meeting.title,
        "source_type": meeting.source_type,
        "language": meeting.language,
        "transcript": meeting.transcript,
        "summary": meeting.summary,
        "participants": meeting.participants or [],
        "created_at": meeting.created_at.isoformat() if meeting.created_at else None,
        "action_items": [
            {"text": a.text, "owner": a.owner, "due_date": a.due_date, "status": a.status}
            for a in meeting.action_items
        ],
        "decisions": [{"text": d.text} for d in meeting.decisions],
    }


def _to_markdown(m: dict) -> str:
    lines = [
        f"# {m['title'] or 'Untitled Meeting'}",
        "",
        f"*Source: {m['source_type']} &middot; Language: {m.get('language') or '—'} &middot; Created: {m['created_at']}*",
        "",
        "## Summary",
        m.get("summary") or "",
        "",
        "## Key Decisions",
    ]
    for d in m.get("decisions", []):
        lines.append(f"- {d['text']}")
    lines += ["", "## Action Items", "| Task | Owner | Due | Status |", "| --- | --- | --- | --- |"]
    for a in m.get("action_items", []):
        lines.append(f"| {a['text']} | {a.get('owner') or '—'} | {a.get('due_date') or '—'} | {a.get('status', 'open')} |")
    lines += ["", "## Participants", ", ".join(m.get("participants", []))]
    lines += ["", "## Transcript", "```", m.get("transcript") or "", "```"]
    return "\n".join(lines)


@router.get("/{meeting_id}/json")
def export_json(meeting_id: int, db: Session = Depends(get_db)):
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    data = _serialize(db, m)
    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}.json"'},
    )


@router.get("/{meeting_id}/markdown", response_class=PlainTextResponse)
def export_markdown(meeting_id: int, db: Session = Depends(get_db)):
    m = crud.get_meeting(db, meeting_id)
    if not m:
        raise HTTPException(status_code=404, detail="Meeting not found")
    md = _to_markdown(_serialize(db, m))
    return PlainTextResponse(
        md,
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}.md"'},
    )
