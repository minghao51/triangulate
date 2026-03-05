"""Tests for Party model."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.storage.models import Base, Party

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_party_with_aliases(db_session):
    """Party can be created with canonical name and aliases."""
    party = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US", "America", "United States", "Trump"],
        description="US government and leadership",
        event_id="event-1"
    )
    db_session.add(party)
    db_session.commit()

    retrieved = db_session.query(Party).filter_by(id="party-1").first()
    assert retrieved.canonical_name == "United States"
    assert retrieved.aliases == ["US", "America", "United States", "Trump"]
    assert retrieved.event_id == "event-1"

def test_party_canonical_name_unique(db_session):
    """Party canonical names must be unique."""
    party1 = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US"],
        event_id="event-1"
    )
    db_session.add(party1)
    db_session.commit()

    party2 = Party(
        id="party-2",
        canonical_name="United States",  # Duplicate
        aliases=["USA"],
        event_id="event-1"
    )
    db_session.add(party2)

    with pytest.raises(Exception):  # Integrity error
        db_session.commit()
