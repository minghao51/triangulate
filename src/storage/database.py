"""Database initialization and session management."""

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

from src.storage.models import Base


class Database:
    """Database connection manager."""

    def __init__(self, db_path: str | None = None):
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
            autocommit=False, autoflush=False, expire_on_commit=False, bind=self.engine
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


def init_database(db_path: str | None = None) -> Database:
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


def read_only_engine(db_path: str | Path):
    """Create an engine that opens an **existing** SQLite file read-only.

    The ``mode=ro`` URI makes SQLite refuse to create a missing file or a
    parent directory, so a probe can never bootstrap storage. The path is
    percent-encoded so spaces, ``#``, ``?`` and ``%`` survive URI parsing. A
    :class:`NullPool` means every session gets a fresh handle and nothing is
    cached across app instances or tests. ``immutable=1`` is deliberately not
    used: the database may be actively written by the server, and its journal
    and locking behavior must stay intact.
    """
    path = Path(db_path)
    if not path.is_absolute():
        path = Path(os.path.abspath(path))
    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    return create_engine(
        f"sqlite:///{uri}&uri=true",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
        echo=False,
    )


@contextmanager
def open_read_only_session(db_path: str | Path) -> Generator[Session, None, None]:
    """Yield a session over an existing database opened in read-only mode.

    The engine is created for this session only and disposed on every path, so
    a missing file, a failed query or a closed client releases the handle. The
    caller owns the transaction (see :func:`begin_read_transaction`); this
    helper never commits.
    """
    engine = read_only_engine(db_path)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def begin_read_transaction(session: Session) -> None:
    """Open an explicit SQLite read transaction for a consistent multi-read view.

    pysqlite's legacy transaction mode only issues ``BEGIN`` before DML, so a
    sequence of SELECTs on its own would each observe the latest committed state.
    Snapshot composition must observe one state, so the caller opens the read
    transaction explicitly before its first read. The caller owns the transaction:
    closing or rolling the session back ends it, and this helper never commits.
    """
    session.connection().exec_driver_sql("BEGIN")


__all__ = [
    "Database",
    "begin_read_transaction",
    "get_database",
    "init_database",
    "open_read_only_session",
    "read_only_engine",
]
