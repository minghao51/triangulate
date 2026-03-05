"""Simple database migration system."""

from sqlalchemy import text
from src.storage.database import get_database


class Migration:
    """A database migration."""

    def __init__(self, version: int, name: str, up: str, down: str = None):
        """Initialize migration.

        Args:
            version: Migration version number
            name: Migration name/description
            up: SQL to apply migration
            down: SQL to rollback migration (optional)
        """
        self.version = version
        self.name = name
        self.up_sql = up
        self.down_sql = down


class MigrationManager:
    """Manage database migrations."""

    def __init__(self, db_path: str = None):
        """Initialize migration manager.

        Args:
            db_path: Path to database file
        """
        self.db = get_database()
        self.migrations_table = "_migrations"
        self._ensure_migrations_table()

    def _ensure_migrations_table(self) -> None:
        """Create migrations tracking table if it doesn't exist."""
        with self.db.get_session_sync() as session:
            session.execute(
                text("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            )
            session.commit()

    def get_current_version(self) -> int:
        """Get the current migration version.

        Returns:
            Current version number (0 if no migrations applied)
        """
        with self.db.get_session_sync() as session:
            result = session.execute(
                text("SELECT MAX(version) FROM _migrations")
            ).scalar()
            return result if result is not None else 0

    def apply_migration(self, migration: Migration) -> None:
        """Apply a migration.

        Args:
            migration: Migration to apply
        """
        current = self.get_current_version()
        if migration.version <= current:
            print(f"Migration {migration.version} already applied")
            return

        print(f"Applying migration {migration.version}: {migration.name}")

        with self.db.get_session_sync() as session:
            # Apply migration SQL
            session.execute(text(migration.up_sql))

            # Record migration
            session.execute(
                text("""
                INSERT INTO _migrations (version, name)
                VALUES (:version, :name)
            """),
                {"version": migration.version, "name": migration.name},
            )

            session.commit()

        print(f"Migration {migration.version} applied successfully")

    def rollback_migration(self, migration: Migration) -> None:
        """Rollback a migration.

        Args:
            migration: Migration to rollback

        Raises:
            ValueError: If migration has no down SQL
        """
        if migration.down_sql is None:
            raise ValueError(f"Migration {migration.version} has no rollback")

        current = self.get_current_version()
        if migration.version != current:
            raise ValueError(
                f"Can only rollback latest migration. "
                f"Current: {current}, Requested: {migration.version}"
            )

        print(f"Rolling back migration {migration.version}: {migration.name}")

        with self.db.get_session_sync() as session:
            # Apply rollback SQL
            session.execute(text(migration.down_sql))

            # Remove migration record
            session.execute(
                text("""
                DELETE FROM _migrations WHERE version = :version
            """),
                {"version": migration.version},
            )

            session.commit()

        print(f"Migration {migration.version} rolled back successfully")


# Define migrations
MIGRATIONS: list[Migration] = [
    # Add future migrations here
    # Migration(
    #     version=1,
    #     name="Initial schema",
    #     up="...",
    #     down="..."
    # )
]


def run_migrations(db_path: str = None) -> None:
    """Run all pending migrations.

    Args:
        db_path: Optional path to database file
    """
    manager = MigrationManager(db_path)

    current = manager.get_current_version()
    print(f"Current database version: {current}")

    for migration in MIGRATIONS:
        if migration.version > current:
            manager.apply_migration(migration)

    print("All migrations applied")


def migrate_add_party_table(session):
    """Add Party table and foreign keys.

    Run this to add party classification support to existing database.

    Args:
        session: SQLAlchemy session
    """
    from src.storage.models import Party, Base

    # Create Party table
    try:
        Party.__table__.create(session.bind)
        print("✓ Created parties table")
    except Exception as e:
        # Table might already exist
        if "already exists" in str(e):
            print("ℹ Parties table already exists")
        else:
            print(f"✗ Error creating parties table: {e}")

    # Add party_id column to claims (may need manual SQL for existing DBs)
    # For SQLite, this typically requires recreating the table
    engine = session.bind
    if engine.dialect.name == "sqlite":
        # SQLite requires special handling for ALTER TABLE
        print("⚠ SQLite detected: Manual migration may be required")
        print("  For existing databases with data, consider:")
        print("  1. Back up your data")
        print("  2. Recreate the database with new schema")
        print("  3. Or manually add party_id column to claims table")
