"""Assemble and persist the structured meeting report.

Takes the extracted action items, decisions, and participants and writes them
to the database, attaching them to the meeting record.
"""
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.db import crud
from app.core.models import Meeting

logger = logging.getLogger(__name__)


def build(db: Session, meeting: Meeting, extracted: Dict[str, Any]) -> Meeting:
    """Persist extracted structured data onto the meeting record.

    Args:
        db: SQLAlchemy session.
        meeting: The meeting ORM object (already has transcript + summary set).
        extracted: Output of ``extractor.extract`` containing keys
            ``action_items``, ``decisions``, ``participants``.

    Returns:
        The updated meeting object.
    """
    action_items = extracted.get("action_items", [])
    decisions = extracted.get("decisions", [])
    participants = extracted.get("participants", [])

    # Replace child collections
    crud.replace_action_items(db, meeting, action_items)
    crud.replace_decisions(db, meeting, decisions)

    # Store participants JSON column
    meeting.participants = participants
    db.commit()
    db.refresh(meeting)

    logger.info(
        "Report built for meeting %s: %d actions, %d decisions, %d participants",
        meeting.id, len(action_items), len(decisions), len(participants),
    )
    return meeting
