# Party Classification System Design

**Date:** 2025-03-05
**Status:** Design Approved

## Overview

Design an AI-based party classification system to normalize messy entity references (e.g., "US", "America", "United States", "Trump") into canonical parties within the triangulation pipeline.

## Architecture

**Pipeline Change:**
```
Article → Collector → [Party Classifier] → Clusterer → Narrator → Classifier
                       ↓                    ↓
                    Party Model          (uses normalized parties)
```

**New Components:**
1. **Party Model** (database) - Stores canonical parties and their aliases
2. **Party Classifier Agent** (AI agent) - LLM-based entity normalization
3. **Party Service** (business logic) - CRUD operations for parties

**Scope:** Parties are per-event scoped (each article processing creates fresh parties)

## Components

### 1. Party Classifier Agent (`src/ai/agents/party_classifier.py`)

**Input:** All unique entities from claims + article context

**LLM Prompt Structure:**
```
Given this article about {topic}:
Article: {title} - {summary}

Extracted entities: {entities}

Group these entities by the real-world party they represent.
For each group, provide:
- canonical_name: The standard name (e.g., "United States")
- aliases: List of all variations found
- reasoning: Brief explanation

Output format (JSON): { "parties": [...] }
```

**Output:** Structured party data with canonical names and aliases

### 2. Party Model (`src/storage/models.py`)

```python
class Party(Base):
    """Normalized political/geographical entities."""
    __tablename__ = "parties"

    id = Column(String, primary_key=True)
    canonical_name = Column(String, nullable=False, unique=True)
    aliases = Column(JSON, nullable=False)  # List of alias strings
    description = Column(Text)
    event_id = Column(String, ForeignKey("events.id"))
    created_at = Column(DateTime(timezone=True), default=utc_now)
```

**Schema Changes:**
- `Claim` table adds: `party_id` (foreign key, nullable)
- `Narrative` table adds: `party_ids` (JSON array)

### 3. Party Service (`src/storage/party_service.py`)

Business logic for party operations:
- `create_parties(event_id, party_data)` - Bulk create parties from LLM output
- `normalize_entity(entity_name, parties)` - Find matching party for a raw entity
- `get_party_mapping(event_id)` - Get entity → party mapping

## Data Flow

1. **Collection**: Extract claims with raw entities in `who` field
2. **Party Classification**:
   - Extract all unique entities
   - Run LLM classifier with article context
   - Store parties in database
3. **Claim Normalization**: Update claims with `party_id` foreign keys
4. **Clustering**: Proceeds with normalized party data
5. **Narration**: Uses pre-normalized parties instead of raw entities

## Error Handling

- **LLM Failure**: Fallback to rule-based string similarity matching
- **Ambiguous Entities**: Leave `party_id` as null, retain raw `who` field
- **Empty/Single Entity**: Create one party per entity or skip if empty
- **Database Errors**: Transaction rollback, continue pipeline without parties

Pipeline continues even if party classification fails - it's an enhancement, not a hard dependency.

## Testing

**Unit Tests:**
- Entity normalization logic (exact match, alias match, no match)
- Bulk party creation

**Integration Tests:**
- LLM-based classification (simple, complex, ambiguous cases)
- Fallback to rule-based matching

**End-to-End Tests:**
- Full workflow with party classification
- Verify claims have `party_id`, narratives have `party_ids`

**Test Cases:**
- US variations: "US", "USA", "America", "United States", "Trump", "Biden"
- Country vs leader: "Iran" vs "Khamenei"
- Organizations: "Pentagon", "US military", "Department of Defense"

## Files to Modify

**New Files:**
- `src/ai/agents/party_classifier.py`
- `src/storage/party_service.py`
- `tests/test_party_classifier.py`
- `tests/test_party_service.py`

**Modified Files:**
- `src/storage/models.py` - Add Party model, update Claim/Narrative
- `src/ai/workflow.py` - Add party classification step
- `src/ai/agents/narrator.py` - Use normalized parties
- `scripts/run_workflow_demo.py` - Display party info in output
