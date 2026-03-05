"""Tests for Claim party foreign key."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.storage.models import Base, Claim, Party

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_claim_has_party_id(db_session):
    """Claim can have a party_id foreign key."""
    party = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US"],
        event_id="event-1"
    )
    db_session.add(party)

    claim = Claim(
        id="claim-1",
        event_id="event-1",
        claim_text="Test claim",
        verification_status="ALLEGED",
        party_id="party-1"
    )
    db_session.add(claim)
    db_session.commit()

    retrieved = db_session.query(Claim).filter_by(id="claim-1").first()
    assert retrieved.party_id == "party-1"

def test_claim_party_id_nullable(db_session):
    """Claim can exist without party_id."""
    claim = Claim(
        id="claim-1",
        event_id="event-1",
        claim_text="Test claim",
        verification_status="ALLEGED"
        # No party_id
    )
    db_session.add(claim)
    db_session.commit()

    retrieved = db_session.query(Claim).filter_by(id="claim-1").first()
    assert retrieved.party_id is None
