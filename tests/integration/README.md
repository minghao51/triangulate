# Integration Tests

This directory contains integration tests that validate the end-to-end functionality of the Triangulate system.

## Running the Tests

### Run all integration tests as pytest:
```bash
uv run pytest tests/integration/ -v
```

### Run specific test:
```bash
uv run pytest tests/integration/test_party_investigation_demo.py -v
```

### Run as demo scripts (for manual exploration):
```bash
uv run python -m tests.integration.test_party_investigation_demo
uv run python -m tests.integration.test_workflow_demo <url>
uv run python -m tests.integration.test_langgraph_demo
```

## Test Files

### `test_party_investigation_demo.py`
Tests the multi-party adversarial investigation workflow where:
- Multiple party investigators analyze claims from different perspectives
- An arbiter reviews findings and makes objective determinations
- Facts are distinguished from allegations with verification status

### `test_workflow_demo.py`
Tests the complete AI workflow pipeline on real article URLs:
- Fetches article content from URL
- Processes through claim extraction, narrative clustering, party classification
- Displays results in human-readable format

### `test_langgraph_demo.py`
Tests the LangGraph StateGraph implementation:
- Validates current workflow implementation
- Demonstrates LangGraph integration with proper state management
- Compares both approaches

## Requirements

- **LLM_API_KEY**: Required for full functionality. Tests will use mock data if not set.
- **Internet connection**: Required for `test_workflow_demo.py` to fetch articles

## Notes

These integration tests serve as both:
1. **Automated tests** - Verify the system works end-to-end
2. **Living documentation** - Show how to use the workflows
