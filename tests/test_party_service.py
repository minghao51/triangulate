"""Tests for Party service."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.storage.models import Base, Party
from src.storage.party_service import PartyService

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

def test_create_parties_from_llm_output(db_session):
    """Service creates parties from LLM classification output."""
    service = PartyService(db_session)

    llm_output = {
        "parties": [
            {
                "canonical_name": "United States",
                "aliases": ["US", "America", "Trump"],
                "reasoning": "All refer to US government"
            },
            {
                "canonical_name": "Iran",
                "aliases": ["Iran", "Tehran"],
                "reasoning": "Iran references"
            }
        ]
    }

    parties = service.create_parties("event-1", llm_output)

    assert len(parties) == 2
    assert parties[0].canonical_name == "United States"
    assert parties[0].aliases == ["US", "America", "Trump"]
    assert parties[1].canonical_name == "Iran"

def test_normalize_entity_finds_party_by_canonical_name(db_session):
    """Service finds party when entity matches canonical name."""
    service = PartyService(db_session)

    party = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US", "America"],
        event_id="event-1"
    )
    db_session.add(party)
    db_session.commit()

    result = service.normalize_entity("United States", "event-1")
    assert result.id == "party-1"

def test_normalize_entity_finds_party_by_alias(db_session):
    """Service finds party when entity matches an alias."""
    service = PartyService(db_session)

    party = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US", "America"],
        event_id="event-1"
    )
    db_session.add(party)
    db_session.commit()

    result = service.normalize_entity("US", "event-1")
    assert result.id == "party-1"

def test_normalize_entity_returns_none_for_unknown(db_session):
    """Service returns None when entity not found."""
    service = PartyService(db_session)

    result = service.normalize_entity("UnknownCountry", "event-1")
    assert result is None

def test_get_party_mapping(db_session):
    """Service returns entity to party ID mapping."""
    service = PartyService(db_session)

    party1 = Party(
        id="party-1",
        canonical_name="United States",
        aliases=["US", "America"],
        event_id="event-1"
    )
    party2 = Party(
        id="party-2",
        canonical_name="Iran",
        aliases=["Tehran"],
        event_id="event-1"
    )
    db_session.add_all([party1, party2])
    db_session.commit()

    mapping = service.get_party_mapping("event-1")

    # Check canonical names are mapped
    assert mapping["United States"] == "party-1"
    assert mapping["Iran"] == "party-2"
    # Check aliases are mapped
    assert mapping["US"] == "party-1"
    assert mapping["America"] == "party-1"
    assert mapping["Tehran"] == "party-2"
