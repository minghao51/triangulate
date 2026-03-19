"""Simple database migration system."""

from sqlalchemy import inspect, text

from src.storage.database import Database, get_database


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
        self.db = Database(db_path) if db_path else get_database()
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
            if migration.version == 1:
                self._apply_party_investigation_schema(session)
            elif migration.version == 2:
                self._apply_case_management_schema(session)
            elif migration.version == 3:
                self._apply_evidence_and_bootstrap_schema(session)
            elif migration.version == 4:
                self._apply_party_provenance_schema(session)
            elif migration.version == 5:
                self._apply_intake_queue_schema(session)
            elif migration.version == 6:
                self._apply_event_location_schema(session)
            else:
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

    def _apply_party_investigation_schema(self, session) -> None:
        """Apply the party investigation schema in an idempotent way.

        The ORM model now includes these fields for fresh databases, so the
        migration must tolerate already-created columns/tables.
        """
        inspector = inspect(session.bind)
        existing_tables = set(inspector.get_table_names())

        if "claims" not in existing_tables:
            raise ValueError("Migration 1 requires the claims table to exist")

        existing_columns = {
            column["name"] for column in inspector.get_columns("claims")
        }
        missing_columns = {
            "fact_allegation_type": "TEXT",
            "arbiter_reasoning": "TEXT",
            "party_positions": "JSON",
            "controversy_score": "FLOAT",
        }

        for column_name, column_type in missing_columns.items():
            if column_name not in existing_columns:
                session.execute(
                    text(
                        f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}"
                    )
                )

        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS party_investigations (
                    id TEXT PRIMARY KEY,
                    event_id TEXT NOT NULL,
                    party_id TEXT NOT NULL,
                    investigation_data JSON NOT NULL,
                    party_stance TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(event_id) REFERENCES events(id),
                    FOREIGN KEY(party_id) REFERENCES parties(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_party_investigation_event_party
                    ON party_investigations (event_id, party_id)
                """
            )
        )

    def _apply_case_management_schema(self, session) -> None:
        """Apply the topic case orchestration schema idempotently."""
        inspector = inspect(session.bind)
        existing_tables = set(inspector.get_table_names())

        if "events" in existing_tables:
            existing_event_columns = {
                column["name"] for column in inspector.get_columns("events")
            }
            if "case_id" not in existing_event_columns:
                session.execute(text("ALTER TABLE events ADD COLUMN case_id TEXT"))
            if "case_run_id" not in existing_event_columns:
                session.execute(text("ALTER TABLE events ADD COLUMN case_run_id TEXT"))

        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS topic_cases (
                    id TEXT PRIMARY KEY,
                    query TEXT NOT NULL,
                    slug TEXT NOT NULL UNIQUE,
                    conflict TEXT,
                    status TEXT NOT NULL,
                    priority INTEGER NOT NULL DEFAULT 0,
                    importance TEXT,
                    routing_mode TEXT,
                    current_stage TEXT,
                    report_path TEXT,
                    latest_manifest_path TEXT,
                    latest_run_started_at TIMESTAMP,
                    latest_run_completed_at TIMESTAMP,
                    last_reviewed_at TIMESTAMP,
                    review_notes TEXT,
                    source_count INTEGER NOT NULL DEFAULT 0,
                    article_count INTEGER NOT NULL DEFAULT 0,
                    event_count INTEGER NOT NULL DEFAULT 0,
                    open_review_items INTEGER NOT NULL DEFAULT 0,
                    metadata_json JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS case_stage_runs (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    duration_ms INTEGER,
                    workflow_name TEXT,
                    model_used TEXT,
                    input_artifact_ids JSON,
                    output_artifact_ids JSON,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    confidence_score FLOAT,
                    controversy_score FLOAT,
                    fallback_count INTEGER NOT NULL DEFAULT 0,
                    parse_failure_count INTEGER NOT NULL DEFAULT 0,
                    cost_estimate_usd FLOAT,
                    metrics_json JSON,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS case_artifacts (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    stage_run_id TEXT NOT NULL,
                    artifact_type TEXT NOT NULL,
                    path TEXT,
                    payload_json JSON,
                    checksum TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id),
                    FOREIGN KEY(stage_run_id) REFERENCES case_stage_runs(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS case_articles (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source TEXT,
                    published_at TEXT,
                    relevance_score FLOAT NOT NULL DEFAULT 0.0,
                    fingerprint TEXT NOT NULL,
                    content TEXT,
                    raw_payload JSON,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'ACTIVE',
                    is_new INTEGER NOT NULL DEFAULT 1,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_case_article_case_url
                    ON case_articles (case_id, url)
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitor_checkpoints (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    monitor_key TEXT NOT NULL,
                    cursor TEXT,
                    last_checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_successful_run_at TIMESTAMP,
                    metadata_json JSON,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id)
                )
                """
            )
        )

    def _apply_intake_queue_schema(self, session) -> None:
        """Apply durable intake queue schema idempotently."""
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS intake_items (
                    id TEXT PRIMARY KEY,
                    case_id TEXT,
                    url TEXT,
                    title TEXT NOT NULL,
                    source_name TEXT,
                    published_at TEXT,
                    fingerprint TEXT NOT NULL,
                    content TEXT,
                    capture_type TEXT NOT NULL DEFAULT 'source_ingest',
                    source_type TEXT NOT NULL DEFAULT 'rss',
                    raw_payload JSON,
                    intake_status TEXT NOT NULL DEFAULT 'PENDING',
                    error_message TEXT,
                    processed_event_id TEXT,
                    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    processed_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id),
                    FOREIGN KEY(processed_event_id) REFERENCES events(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_intake_items_case_id
                    ON intake_items (case_id)
                """
            )
        )
        session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_intake_items_fingerprint
                    ON intake_items (fingerprint)
                """
            )
        )
        session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_intake_items_intake_status
                    ON intake_items (intake_status)
                """
            )
        )
        session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_intake_items_processed_event_id
                    ON intake_items (processed_event_id)
                """
            )
        )

    def _apply_event_location_schema(self, session) -> None:
        """Add event location columns if they are missing."""
        inspector = inspect(session.bind)
        existing_tables = set(inspector.get_table_names())
        if "events" not in existing_tables:
            return
        existing_columns = {column["name"] for column in inspector.get_columns("events")}
        missing_columns = {
            "location_country_code": "TEXT",
            "location_lat": "REAL",
            "location_lon": "REAL",
        }
        for column_name, column_type in missing_columns.items():
            if column_name not in existing_columns:
                session.execute(
                    text(f"ALTER TABLE events ADD COLUMN {column_name} {column_type}")
                )
        session.execute(
            text(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_monitor_checkpoint
                    ON monitor_checkpoints (case_id, monitor_key)
                """
            )
        )

    def _apply_evidence_and_bootstrap_schema(self, session) -> None:
        """Apply schema for evidence objects and richer case state."""
        inspector = inspect(session.bind)
        existing_tables = set(inspector.get_table_names())

        if "claims" in existing_tables:
            existing_claim_columns = {
                column["name"] for column in inspector.get_columns("claims")
            }
            claim_columns = {
                "claim_signature": "TEXT",
                "support_count": "INTEGER NOT NULL DEFAULT 0",
                "oppose_count": "INTEGER NOT NULL DEFAULT 0",
                "source_diversity_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for column_name, column_type in claim_columns.items():
                if column_name not in existing_claim_columns:
                    session.execute(
                        text(
                            f"ALTER TABLE claims ADD COLUMN {column_name} {column_type}"
                        )
                    )
            session.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS ix_claims_claim_signature
                        ON claims (claim_signature)
                    """
                )
            )

        if "case_articles" in existing_tables:
            existing_case_article_columns = {
                column["name"] for column in inspector.get_columns("case_articles")
            }
            article_columns = {
                "source_type": "TEXT NOT NULL DEFAULT 'rss'",
                "source_metadata": "JSON",
            }
            for column_name, column_type in article_columns.items():
                if column_name not in existing_case_article_columns:
                    session.execute(
                        text(
                            f"ALTER TABLE case_articles ADD COLUMN {column_name} {column_type}"
                        )
                    )

        if "parties" in existing_tables:
            existing_party_columns = {
                column["name"] for column in inspector.get_columns("parties")
            }
            if "is_bootstrap_confirmed" not in existing_party_columns:
                session.execute(
                    text(
                        "ALTER TABLE parties ADD COLUMN is_bootstrap_confirmed INTEGER NOT NULL DEFAULT 0"
                    )
                )

        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS evidence_items (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    event_id TEXT,
                    case_article_id TEXT,
                    evidence_type TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    title TEXT,
                    origin_url TEXT,
                    canonical_url TEXT,
                    archived_url TEXT,
                    publisher TEXT,
                    published_at TEXT,
                    content TEXT,
                    capture_metadata JSON,
                    verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
                    credibility_tier TEXT,
                    requires_human_review INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(case_id) REFERENCES topic_cases(id),
                    FOREIGN KEY(event_id) REFERENCES events(id),
                    FOREIGN KEY(case_article_id) REFERENCES case_articles(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS evidence_verification_checks (
                    id TEXT PRIMARY KEY,
                    evidence_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    result TEXT NOT NULL,
                    method TEXT,
                    notes TEXT,
                    verified_by TEXT,
                    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS claim_evidence_links (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    source_diversity_rank INTEGER NOT NULL DEFAULT 1,
                    confidence_score FLOAT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(claim_id) REFERENCES claims(id),
                    FOREIGN KEY(evidence_id) REFERENCES evidence_items(id)
                )
                """
            )
        )
        session.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS ix_claim_evidence_links_claim_id
                    ON claim_evidence_links (claim_id)
                """
            )
        )

    def _apply_party_provenance_schema(self, session) -> None:
        """Persist bootstrap party provenance without assuming column absence."""
        inspector = inspect(session.bind)
        existing_tables = set(inspector.get_table_names())

        if "parties" not in existing_tables:
            return

        existing_party_columns = {
            column["name"] for column in inspector.get_columns("parties")
        }
        if "is_bootstrap_confirmed" not in existing_party_columns:
            session.execute(
                text(
                    "ALTER TABLE parties ADD COLUMN is_bootstrap_confirmed INTEGER NOT NULL DEFAULT 0"
                )
            )

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
    Migration(
        version=1,
        name="Add party investigation schema",
        up="""
        ALTER TABLE claims ADD COLUMN fact_allegation_type TEXT;
        ALTER TABLE claims ADD COLUMN arbiter_reasoning TEXT;
        ALTER TABLE claims ADD COLUMN party_positions JSON;
        ALTER TABLE claims ADD COLUMN controversy_score FLOAT;

        CREATE TABLE IF NOT EXISTS party_investigations (
            id TEXT PRIMARY KEY,
            event_id TEXT NOT NULL,
            party_id TEXT NOT NULL,
            investigation_data JSON NOT NULL,
            party_stance TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(event_id) REFERENCES events(id),
            FOREIGN KEY(party_id) REFERENCES parties(id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_party_investigation_event_party
            ON party_investigations (event_id, party_id);
        """,
        down="""
        DROP INDEX IF EXISTS uq_party_investigation_event_party;
        DROP TABLE IF EXISTS party_investigations;
        """,
    ),
    Migration(
        version=2,
        name="Add topic case orchestration schema",
        up="""
        CREATE TABLE IF NOT EXISTS topic_cases (
            id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            conflict TEXT,
            status TEXT NOT NULL
        );
        """,
        down="""
        DROP INDEX IF EXISTS uq_monitor_checkpoint;
        DROP INDEX IF EXISTS uq_case_article_case_url;
        DROP TABLE IF EXISTS monitor_checkpoints;
        DROP TABLE IF EXISTS case_articles;
        DROP TABLE IF EXISTS case_artifacts;
        DROP TABLE IF EXISTS case_stage_runs;
        DROP TABLE IF EXISTS topic_cases;
        """,
    ),
    Migration(
        version=3,
        name="Add evidence objects and bootstrap metadata schema",
        up="""
        ALTER TABLE claims ADD COLUMN claim_signature TEXT;
        ALTER TABLE claims ADD COLUMN support_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE claims ADD COLUMN oppose_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE claims ADD COLUMN source_diversity_count INTEGER NOT NULL DEFAULT 0;
        ALTER TABLE case_articles ADD COLUMN source_type TEXT NOT NULL DEFAULT 'rss';
        ALTER TABLE case_articles ADD COLUMN source_metadata JSON;
        CREATE TABLE IF NOT EXISTS evidence_items (
            id TEXT PRIMARY KEY,
            case_id TEXT NOT NULL,
            event_id TEXT,
            case_article_id TEXT,
            evidence_type TEXT NOT NULL,
            source_type TEXT NOT NULL,
            title TEXT,
            origin_url TEXT,
            canonical_url TEXT,
            archived_url TEXT,
            publisher TEXT,
            published_at TEXT,
            content TEXT,
            capture_metadata JSON,
            verification_status TEXT NOT NULL DEFAULT 'UNVERIFIED',
            credibility_tier TEXT,
            requires_human_review INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS evidence_verification_checks (
            id TEXT PRIMARY KEY,
            evidence_id TEXT NOT NULL,
            check_type TEXT NOT NULL,
            result TEXT NOT NULL,
            method TEXT,
            notes TEXT,
            verified_by TEXT,
            verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS claim_evidence_links (
            id TEXT PRIMARY KEY,
            claim_id TEXT NOT NULL,
            evidence_id TEXT NOT NULL,
            relation TEXT NOT NULL,
            source_diversity_rank INTEGER NOT NULL DEFAULT 1,
            confidence_score FLOAT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """,
        down="""
        DROP INDEX IF EXISTS ix_claim_evidence_links_claim_id;
        DROP TABLE IF EXISTS claim_evidence_links;
        DROP TABLE IF EXISTS evidence_verification_checks;
        DROP TABLE IF EXISTS evidence_items;
        """,
    ),
    Migration(
        version=4,
        name="Persist party provenance metadata",
        up="""
        ALTER TABLE parties ADD COLUMN is_bootstrap_confirmed INTEGER NOT NULL DEFAULT 0;
        """,
        down="""
        """,
    ),
    Migration(
        version=5,
        name="Add durable intake queue",
        up="""
        CREATE TABLE IF NOT EXISTS intake_items (
            id TEXT PRIMARY KEY,
            case_id TEXT,
            url TEXT,
            title TEXT NOT NULL,
            source_name TEXT,
            published_at TEXT,
            fingerprint TEXT NOT NULL,
            content TEXT,
            capture_type TEXT NOT NULL DEFAULT 'source_ingest',
            source_type TEXT NOT NULL DEFAULT 'rss',
            raw_payload JSON,
            intake_status TEXT NOT NULL DEFAULT 'PENDING',
            error_message TEXT,
            processed_event_id TEXT,
            first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(case_id) REFERENCES topic_cases(id),
            FOREIGN KEY(processed_event_id) REFERENCES events(id)
        );
        CREATE INDEX IF NOT EXISTS ix_intake_items_case_id ON intake_items (case_id);
        CREATE INDEX IF NOT EXISTS ix_intake_items_fingerprint ON intake_items (fingerprint);
        CREATE INDEX IF NOT EXISTS ix_intake_items_intake_status ON intake_items (intake_status);
        CREATE INDEX IF NOT EXISTS ix_intake_items_processed_event_id ON intake_items (processed_event_id);
        """,
        down="""
        DROP INDEX IF EXISTS ix_intake_items_processed_event_id;
        DROP INDEX IF EXISTS ix_intake_items_intake_status;
        DROP INDEX IF EXISTS ix_intake_items_fingerprint;
        DROP INDEX IF EXISTS ix_intake_items_case_id;
        DROP TABLE IF EXISTS intake_items;
        """,
    ),
    Migration(
        version=6,
        name="Add location columns to events",
        up="""
        ALTER TABLE events ADD COLUMN location_country_code TEXT;
        ALTER TABLE events ADD COLUMN location_lat REAL;
        ALTER TABLE events ADD COLUMN location_lon REAL;
        """,
        down="""
        """,
    ),
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
    from src.storage.models import Party

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
