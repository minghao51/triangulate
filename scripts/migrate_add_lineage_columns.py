"""Migration script to add new columns for data lineage tracing.

Run this script once to update your existing database schema.
"""
import sqlite3
import sys

def migrate(db_path: str = "triangulate.db"):
    """Apply migration to add new columns."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations = [
        # Events table - add workflow_route and source_url
        ("ALTER TABLE events ADD COLUMN workflow_route TEXT",),
        ("ALTER TABLE events ADD COLUMN source_url TEXT",),

        # Narratives table - add key_themes and main_entities
        ("ALTER TABLE narratives ADD COLUMN key_themes TEXT DEFAULT '[]'",),
        ("ALTER TABLE narratives ADD COLUMN main_entities TEXT DEFAULT '[]'",),

        # Party investigations table - add party_name
        ("ALTER TABLE party_investigations ADD COLUMN party_name TEXT",),
    ]

    for sql, in migrations:
        table = sql.split(" TABLE ")[1].split(" ")[0]
        col = sql.split(" ADD COLUMN ")[1].split(" ")[0]
        try:
            cursor.execute(sql)
            print(f"✓ Added {col} to {table}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print(f"○ Skipped {col} in {table} (already exists)")
            else:
                raise

    conn.commit()
    conn.close()
    print("\n✓ Migration complete!")


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "triangulate.db"
    migrate(db_path)
