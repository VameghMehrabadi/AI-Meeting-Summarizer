"""Database engine and session setup."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import DB_PATH

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Create all tables and run lightweight migrations. Called on app startup."""
    # Import models so they register with Base.metadata
    from app.core import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Add columns that may be missing in older SQLite databases."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "meetings" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("meetings")}
    if "language" not in existing:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE meetings ADD COLUMN language VARCHAR(8)"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
