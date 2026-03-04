"""Database initialization and session management."""

import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from src.storage.models import Base


class Database:
    """Database connection manager."""

    def __init__(self, db_path: str = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Defaults to config or ./triangulate.db
        """
        if db_path is None:
            db_path = os.getenv("DATABASE_PATH", "./triangulate.db")

        # Ensure directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
            echo=False,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def init_db(self) -> None:
        """Create all tables in the database."""
        Base.metadata.create_all(bind=self.engine)

    def drop_all(self) -> None:
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session.

        Yields:
            SQLAlchemy session
        """
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def get_session_sync(self) -> Session:
        """Get a database session synchronously.

        Returns:
            SQLAlchemy session
        """
        return self.SessionLocal()


# Global database instance
_db: Database | None = None


def get_database() -> Database:
    """Get the global database instance.

    Returns:
        Database instance
    """
    global _db
    if _db is None:
        _db = Database()
    return _db


def init_database(db_path: str = None) -> Database:
    """Initialize the database.

    Args:
        db_path: Optional path to database file

    Returns:
        Initialized Database instance
    """
    db = Database(db_path)
    db.init_db()
    global _db
    _db = db
    return db
