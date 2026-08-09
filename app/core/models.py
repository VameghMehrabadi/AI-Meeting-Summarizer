"""SQLAlchemy ORM models for meetings, action items, and decisions."""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.db.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=True)
    source_type = Column(String(16), nullable=False)  # "audio" or "text"
    language = Column(String(8), nullable=True)      # "en" or "fa" (detected)
    audio_path = Column(String(512), nullable=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    participants = Column(JSON, nullable=True)        # list[str]
    status = Column(String(32), default="pending")    # pending|transcribing|preprocessing|summarizing|extracting|building|done|error
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    action_items = relationship("ActionItem", back_populates="meeting", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="meeting", cascade="all, delete-orphan")


class ActionItem(Base):
    __tablename__ = "action_items"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)
    owner = Column(String(255), nullable=True)
    due_date = Column(String(64), nullable=True)      # ISO date string or relative phrase
    status = Column(String(32), default="open")      # open|done|blocked

    meeting = relationship("Meeting", back_populates="action_items")


class Decision(Base):
    __tablename__ = "decisions"

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    text = Column(Text, nullable=False)

    meeting = relationship("Meeting", back_populates="decisions")
