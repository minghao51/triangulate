"""S01 transactional case search-index contract tests."""
from datetime import datetime, timezone
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import text

from src.storage.database import Database
from src.storage.migrations import MIGRATIONS, MigrationManager, run_migrations
from src.storage.models import (
    CaseStatus, Claim, Event, EvidenceItem, TopicCase, VerificationStatus,
)
from src.storage.captures import record_evidence_capture
from src.storage.search import (
    delete_index_row, deterministic_rowid, probe_search_capability,
    rebuild_case_search_index, sync_evidence_index, sync_event_index,
    upsert_index_row,
)
from src.storage.write_guard import claim_case_ownership, new_writer_token


def _db(tmp_path):
    db = Database(str(tmp_path / "search.sqlite"))
    db.init_db()
    run_migrations(str(tmp_path / "search.sqlite"))
    return db


def _case(session, key):
    session.add(TopicCase(id=key, query=key, slug=key, status=CaseStatus.DISCOVERING))
    session.flush()
    event = Event(id=f"event-{key}", timestamp=datetime.now(timezone.utc), title="Timeline",
                  summary="summary", verification_status=VerificationStatus.ALLEGED, case_id=key)
    session.add(event)
    session.flush()
    evidence = EvidenceItem(id=f"evidence-{key}", case_id=key, event_id=event.id,
                            evidence_type="article", source_type="test", title="Copper harbor", publisher="Press")
    session.add(evidence)
    session.flush()
    record_evidence_capture(session, evidence, text="Obsidian lighthouse body")
    claim = Claim(id=f"claim-{key}", event_id=event.id, claim_text="Quartz claim text",
                  verification_status=VerificationStatus.ALLEGED, claim_signature="sig")
    session.add(claim)
    session.flush()
    sync_event_index(session, event.id)
    return event, evidence, claim


def _dump(session):
    return tuple(tuple(row) for row in session.execute(text(
        "SELECT case_id,entity_type,entity_id,title,body,signature,event_id,party_id,publisher,status,published_at "
        "FROM case_search_index ORDER BY case_id,entity_type,entity_id"
    )))


def test_current_evidence_and_claim_index_updates_and_rollback(tmp_path):
    db = _db(tmp_path)
    with db.get_session_sync() as session:
        event, evidence, claim = _case(session, "A")
        assert probe_search_capability(session).available
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Obsidian'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Quartz'")).scalar() == 1
        session.commit()
        before = _dump(session)
        record_evidence_capture(session, evidence, text="Replacement glacier body")
        claim.claim_text = "Replaced zircon assertion"
        session.flush()
        sync_event_index(session, event.id)
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Obsidian'")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'glacier'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Quartz'")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'zircon'")).scalar() == 1
        session.delete(claim)
        session.flush()
        sync_event_index(session, event.id)
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE entity_id=:id"), {"id": claim.id}).scalar() == 0
        session.rollback()
        assert _dump(session) == before
        session.close()


def test_rebuild_case_scope_idempotency_and_active_writer_refusal(tmp_path, monkeypatch):
    db = _db(tmp_path)
    with db.get_session_sync() as session:
        _case(session, "A")
        _case(session, "B")
        first = rebuild_case_search_index(session, "A")
        dump = _dump(session)
        second = rebuild_case_search_index(session, "A")
        assert first["counts"] == second["counts"] == {"evidence": 1, "claim": 1}
        assert _dump(session) == dump
        token = new_writer_token()
        claim_case_ownership(session, "A", token=token, kind="run", ref_id="foreign")
        session.commit()
    # Exercise the real CLI entry point: its admission failure cannot mutate either case.
    import src.cli.commands.cases as case_commands
    from src.cli.commands.cases import cmd_rebuild_case_search

    monkeypatch.setattr(case_commands, "get_database", lambda: db)
    with db.get_session_sync() as session:
        before = _dump(session)
        from typer import Exit
        with pytest.raises(Exit):
            cmd_rebuild_case_search("A")
        assert _dump(session) == before
        assert {r[0] for r in before} == {"A", "B"}


def test_targeted_index_upsert_delete_and_deterministic_rowid(tmp_path):
    db = _db(tmp_path)
    row = {
        "case_id": "A", "entity_type": "evidence", "entity_id": "one",
        "title": "first", "body": "initial searchable phrase", "signature": "",
        "event_id": "", "party_id": "", "publisher": "", "status": "",
        "published_at": "",
    }
    with db.get_session_sync() as session:
        first_id = deterministic_rowid("evidence", "one")
        assert first_id == deterministic_rowid("evidence", "one")
        other_process = subprocess.check_output(
            [sys.executable, "-c", "from src.storage.search import deterministic_rowid; print(deterministic_rowid('evidence', 'one'))"],
            text=True,
        ).strip()
        assert first_id == int(other_process)
        upsert_index_row(session, row)
        upsert_index_row(session, {**row, "body": "replacement searchable phrase"})
        other = {**row, "entity_id": "two", "body": "untouched searchable phrase"}
        upsert_index_row(session, other)
        assert session.execute(text("SELECT rowid FROM case_search_index WHERE entity_id='one'")).scalar() == first_id
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'initial'")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'replacement'")).scalar() == 1
        delete_index_row(session, "A", "evidence", "one")
        assert session.execute(text("SELECT entity_id FROM case_search_index")).scalars().all() == ["two"]
        session.commit()
        # A real source entity retains its rowid when a case is rebuilt.
        _case(session, "B")
        rowid_before_rebuild = session.execute(
            text("SELECT rowid FROM case_search_index WHERE entity_id='evidence-B'")
        ).scalar()
        rebuild_case_search_index(session, "B")
        rowid_after_rebuild = session.execute(
            text("SELECT rowid FROM case_search_index WHERE entity_id='evidence-B'")
        ).scalar()
        assert rowid_after_rebuild == rowid_before_rebuild


def test_standalone_evidence_becoming_event_owned_reuses_one_row(tmp_path):
    db = _db(tmp_path)
    with db.get_session_sync() as session:
        session.add(TopicCase(id="A", query="A", slug="A", status=CaseStatus.DISCOVERING))
        evidence = EvidenceItem(id="moving-evidence", case_id="A", event_id=None,
                                evidence_type="article", source_type="test", title="Standalone")
        session.add(evidence)
        session.flush()
        record_evidence_capture(session, evidence, text="Standalone becomes owned")
        sync_evidence_index(session, evidence)
        event = Event(id="moving-event", timestamp=datetime.now(timezone.utc), title="Event",
                      summary="", verification_status=VerificationStatus.ALLEGED, case_id="A")
        session.add(event)
        session.flush()
        evidence.event_id = event.id
        session.flush()
        sync_event_index(session, event.id)
        rows = session.execute(text("SELECT rowid,event_id FROM case_search_index WHERE entity_id='moving-evidence'")).all()
        assert len(rows) == 1
        assert rows[0][1] == event.id


def test_missing_index_is_explicit_capability_state_and_migration_completes(tmp_path):
    path = str(tmp_path / "no-fts.sqlite")
    db = Database(path)
    db.init_db()
    manager = MigrationManager(path)
    for migration in MIGRATIONS[:-1]:
        manager.apply_migration(migration)

    raw = manager.db.engine.raw_connection()
    raw.set_authorizer(
        lambda action, arg1, arg2, database, trigger: (
            sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_CREATE_VTABLE
            else sqlite3.SQLITE_OK
        )
    )
    raw.close()
    with pytest.raises(Exception, match="not authorized"):
        manager.apply_migration(MIGRATIONS[-1])
    assert manager.get_current_version() == 14
    with manager.db.get_session_sync() as session:
        capability = probe_search_capability(session)
        assert capability.available is False
        assert capability.reason == "FTS5 module is available, but case_search_index is missing (migration 15 is not applied)."


def _event_payload(event_id, *, claim_text: str | None = "Claimable claim phrase", body="Current capture phrase"): 
    return {
        "id": event_id,
        "timestamp": datetime.now(timezone.utc),
        "title": "Indexed event",
        "summary": "event summary",
        "verification_status": "ALLEGED",
        "evidence": [{"id": "evidence-live", "title": "Cobalt title phrase", "content": body,
                      "publisher": "Daily Press", "canonical_url": "https://example.test/live"}],
        "claims": ([{"id": "claim-live", "claim_text": claim_text,
                     "verification_status": "ALLEGED", "claim_signature": "signature-original"}]
                   if claim_text else []),
    }


def test_store_event_own_session_indexes_rewrites_and_removes_claim(tmp_path, monkeypatch):
    db = _db(tmp_path)
    import src.storage.event_store as event_store
    monkeypatch.setattr(event_store, "get_database", lambda: db)
    with db.get_session_sync() as session:
        session.add(TopicCase(id="A", query="A", slug="A", status=CaseStatus.DISCOVERING))
        session.commit()

    assert event_store.store_event_in_db(_event_payload("event-live"), case_id="A")
    with db.get_session_sync() as session:
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE title MATCH 'Cobalt'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Current' AND entity_type='evidence'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Claimable'")).scalar() == 1

    assert event_store.store_event_in_db(
        _event_payload("event-live", claim_text="Rewritten indigo assertion", body="Fresh capture content"), case_id="A"
    )
    with db.get_session_sync() as session:
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Current'")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Claimable'")).scalar() == 0
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Fresh'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'indigo'")).scalar() == 1

    assert event_store.store_event_in_db(_event_payload("event-live", claim_text=None), case_id="A")
    with db.get_session_sync() as session:
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE entity_type='claim'")).scalar() == 0


def test_store_event_caller_session_index_is_atomic(tmp_path, monkeypatch):
    db = _db(tmp_path)
    import src.storage.event_store as event_store
    monkeypatch.setattr(event_store, "get_database", lambda: db)
    with db.get_session_sync() as session:
        session.add(TopicCase(id="A", query="A", slug="A", status=CaseStatus.DISCOVERING))
        session.commit()
    assert event_store.store_event_in_db(_event_payload("event-atomic"), case_id="A")
    with db.get_session_sync() as session:
        before = _dump(session)
        assert event_store.store_event_in_db(
            _event_payload("event-atomic", claim_text="Temporary cobalt claim", body="Temporary capture"),
            case_id="A", session=session,
        )
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'Temporary'")).scalar() == 2
        session.rollback()
        assert _dump(session) == before


def test_osint_service_indexes_standalone_evidence_idempotently(tmp_path, monkeypatch):
    import src.cases.service as case_service_module
    from src.cases.service import TopicCaseService

    db = _db(tmp_path)
    monkeypatch.setattr(case_service_module, "get_database", lambda: db)
    with db.get_session_sync() as session:
        session.add(TopicCase(id="OSINT", query="OSINT", slug="osint", status=CaseStatus.DISCOVERING))
        session.commit()
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("Standalone capture searchable phrase", encoding="utf-8")
    service = TopicCaseService.__new__(TopicCaseService)
    monkeypatch.setattr(service, "_refresh_case_metrics", lambda *_args: None)
    service.ingest_osint_artifact(tool="test-tool", file_path=artifact, case_id="OSINT")
    with db.get_session_sync() as session:
        first = _dump(session)
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'searchable'")).scalar() == 1
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE event_id=''")).scalar() == 1
    service.ingest_osint_artifact(tool="test-tool", file_path=artifact, case_id="OSINT")
    with db.get_session_sync() as session:
        assert _dump(session) == first


def test_unowned_event_sync_leaves_no_index_rows(tmp_path):
    db = _db(tmp_path)
    with db.get_session_sync() as session:
        event, evidence, claim = _case(session, "owned")
        session.commit()
        event.case_id = None
        session.flush()
        sync_event_index(session, event.id)
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE event_id=:event"),
                               {"event": event.id}).scalar() == 0
        session.rollback()


def test_legacy_v14_migration_15_creates_working_index(tmp_path):
    path = str(tmp_path / "legacy-v14.sqlite")
    db = Database(path)
    db.init_db()
    manager = MigrationManager(path)
    for migration in MIGRATIONS[:-1]:
        manager.apply_migration(migration)
    assert manager.get_current_version() == 14
    manager.apply_migration(MIGRATIONS[-1])
    with manager.db.get_session_sync() as session:
        assert session.execute(text("SELECT 1 FROM sqlite_master WHERE name='case_search_index'")).first()
        assert probe_search_capability(session).available
        session.add(TopicCase(id="legacy", query="legacy", slug="legacy", status=CaseStatus.DISCOVERING))
        session.flush()
        event = Event(id="legacy-event", timestamp=datetime.now(timezone.utc), title="Legacy", summary="",
                      verification_status=VerificationStatus.ALLEGED, case_id="legacy")
        session.add(event)
        session.flush()
        claim = Claim(id="legacy-claim", event_id=event.id, claim_text="Legacy migration term",
                      verification_status=VerificationStatus.ALLEGED)
        session.add(claim)
        session.flush()
        sync_event_index(session, event.id)
        assert session.execute(text("SELECT count(*) FROM case_search_index WHERE body MATCH 'migration'")).scalar() == 1


def test_signature_backfill_resynchronizes_claim_metadata(tmp_path):
    from src.cases._support import _recompute_case_claim_aggregates

    db = _db(tmp_path)
    with db.get_session_sync() as session:
        session.add(TopicCase(id="sig-case", query="sig", slug="sig", status=CaseStatus.DISCOVERING))
        event = Event(id="sig-event", timestamp=datetime.now(timezone.utc), title="Signature",
                      summary="", verification_status=VerificationStatus.ALLEGED, case_id="sig-case")
        session.add(event)
        session.flush()
        claim = Claim(id="sig-claim", event_id=event.id, claim_text="Backfilled signature text",
                      verification_status=VerificationStatus.ALLEGED)
        session.add(claim)
        session.flush()
        sync_event_index(session, event.id)
        assert session.execute(text("SELECT signature FROM case_search_index WHERE entity_id='sig-claim'")).scalar() == ""
        _recompute_case_claim_aggregates(session, "sig-case")
        stored_signature = session.execute(text("SELECT signature FROM case_search_index WHERE entity_id='sig-claim'")).scalar()
        assert stored_signature == claim.claim_signature
        assert stored_signature


def test_probe_propagates_database_errors(tmp_path, monkeypatch):
    db = _db(tmp_path)
    with db.get_session_sync() as session:
        original_execute = session.execute
        calls = 0

        def broken_execute(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("database I/O failure")
            return original_execute(*args, **kwargs)

        monkeypatch.setattr(session, "execute", broken_execute)
        with pytest.raises(RuntimeError, match="database I/O failure"):
            probe_search_capability(session)


def test_probe_distinguishes_missing_fts5_module(tmp_path, monkeypatch):
    import src.storage.search as search

    db = _db(tmp_path)
    with db.get_session_sync() as session:
        monkeypatch.setattr(search, "_fts5_module_available", lambda _session: False)
        capability = probe_search_capability(session)
        assert capability == search.SearchCapability(
            False, "SQLite FTS5 module is not compiled into this SQLite build."
        )
