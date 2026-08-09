"""CRUD helpers for meetings, action items, and decisions."""
from typing import Optional, List

from sqlalchemy.orm import Session

from app.core.models import Meeting, ActionItem, Decision


def create_meeting(db: Session, *, title: Optional[str], source_type: str, audio_path: Optional[str] = None, transcript: Optional[str] = None, status: str = "pending") -> Meeting:
    m = Meeting(title=title, source_type=source_type, audio_path=audio_path, transcript=transcript, status=status)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def get_meeting(db: Session, meeting_id: int) -> Optional[Meeting]:
    return db.get(Meeting, meeting_id)


def list_meetings(db: Session) -> List[Meeting]:
    return db.query(Meeting).order_by(Meeting.created_at.desc()).all()


def update_meeting(db: Session, meeting: Meeting, **fields) -> Meeting:
    for k, v in fields.items():
        setattr(meeting, k, v)
    db.commit()
    db.refresh(meeting)
    return meeting


def delete_meeting(db: Session, meeting: Meeting) -> None:
    db.delete(meeting)
    db.commit()


def replace_action_items(db: Session, meeting: Meeting, items: List[dict]) -> None:
    db.query(ActionItem).filter(ActionItem.meeting_id == meeting.id).delete()
    for it in items:
        db.add(ActionItem(
            meeting_id=meeting.id,
            text=it.get("text", ""),
            owner=it.get("owner"),
            due_date=it.get("due_date"),
            status=it.get("status", "open"),
        ))
    db.commit()


def replace_decisions(db: Session, meeting: Meeting, decisions: List[dict]) -> None:
    db.query(Decision).filter(Decision.meeting_id == meeting.id).delete()
    for d in decisions:
        db.add(Decision(meeting_id=meeting.id, text=d.get("text", "")))
    db.commit()
