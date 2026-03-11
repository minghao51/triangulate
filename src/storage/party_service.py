"""Party service for CRUD operations."""

import logging
import uuid
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.storage.models import Party

logger = logging.getLogger(__name__)


class PartyService:
    """Business logic for party operations."""

    def __init__(self, session: Session):
        """Initialize party service.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def create_parties(self, event_id: str, party_data: dict[str, Any]) -> List[Party]:
        """Bulk create parties from LLM classification output.

        Args:
            event_id: Event identifier
            party_data: LLM output with "parties" list

        Returns:
            List of created Party objects
        """
        parties = []
        for party_info in party_data.get("parties", []):
            canonical_name = party_info["canonical_name"]
            party = (
                self.session.query(Party)
                .filter_by(canonical_name=canonical_name)
                .first()
            )
            if party is None:
                party = Party(
                    id=str(uuid.uuid4()),
                    canonical_name=canonical_name,
                    aliases=party_info["aliases"],
                    description=party_info.get("reasoning", ""),
                    event_id=event_id,
                )
                self.session.add(party)
            else:
                merged_aliases = list(
                    dict.fromkeys(
                        [*party.aliases, *party_info.get("aliases", []), canonical_name]
                    )
                )
                party.aliases = merged_aliases
                if party_info.get("reasoning"):
                    party.description = party_info["reasoning"]
                party.event_id = event_id
            parties.append(party)

        self.session.commit()
        logger.info(f"Created {len(parties)} parties for event {event_id}")
        return parties

    def _get_candidate_parties(self, event_id: str) -> List[Party]:
        """Load parties for an event, falling back to global records if needed."""
        parties = self.session.query(Party).filter_by(event_id=event_id).all()
        if parties:
            return parties
        return self.session.query(Party).all()

    def normalize_entity(self, entity_name: str, event_id: str) -> Optional[Party]:
        """Find the party that claims this entity.

        Args:
            entity_name: Raw entity string from claims
            event_id: Event identifier

        Returns:
            Party object if found, None otherwise
        """
        parties = self._get_candidate_parties(event_id)

        for party in parties:
            if entity_name == party.canonical_name or entity_name in party.aliases:
                return party

        return None

    def get_party_mapping(self, event_id: str) -> dict[str, str]:
        """Get entity -> party ID mapping for an event.

        Args:
            event_id: Event identifier

        Returns:
            Dictionary mapping entity names to party IDs
        """
        parties = self._get_candidate_parties(event_id)

        mapping = {}
        for party in parties:
            # Map canonical name
            mapping[party.canonical_name] = party.id
            # Map all aliases
            for alias in party.aliases:
                mapping[alias] = party.id

        return mapping
