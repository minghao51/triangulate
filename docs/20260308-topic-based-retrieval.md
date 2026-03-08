# AI-Powered Topic-Based News Retrieval

**Created:** 20260308

## Overview

This document describes the AI-powered topic-based news retrieval system that enables intelligent fetching and analysis of news articles by topic, leveraging the 164 media sources organized by conflict in `/data/`.

## Features

### 1. Intelligent Conflict Detection

The system automatically detects which conflict context (Gaza, Ukraine, Iran) applies to a given topic using AI analysis.

**Example:**
```python
from src.ai.topic_analyzer import TopicAnalyzer

analyzer = TopicAnalyzer(config)
conflict = await analyzer.detect_conflict("Gaza ceasefire negotiations")
# Returns: "gaza_war"
```

### 2. AI-Powered Query Generation

The system generates 5-10 relevant search queries for each topic, including:
- Different keywords and phrases
- Names of key parties/entities
- Various aspects and perspectives
- Both broad and specific terms

### 3. Source Prioritization

Media sources are scored by relevance to the topic (0-1 scale) and prioritized accordingly.

### 4. Article Relevance Scoring

Each fetched article is scored for semantic similarity to the topic, with low-relevance articles filtered out.

### 5. Multi-Party Analysis

Articles are processed through the existing multi-party adversarial AI workflow, providing:
- Claim extraction
- Narrative clustering
- Party classification
- Verification status assignment

## Usage

### CLI Command

```bash
# Basic usage
uv run triangulate fetch-topic "Gaza ceasefire negotiations"

# With options
uv run triangulate fetch-topic "Gaza ceasefire" \
  --output ./results \
  --format json,markdown \
  --max-articles 50 \
  --relevance-threshold 0.4 \
  --conflict gaza_war
```

**Flags:**
- `--output DIR`: Output directory (default: ./output)
- `--format FORMATS`: Comma-separated formats (json,markdown)
- `--max-articles INT`: Maximum articles to fetch (default: 50)
- `--relevance-threshold FLOAT`: Minimum relevance score 0-1 (default: 0.3)
- `--conflict FOLDER`: Override auto-detection (gaza_war, ukraine_war, iran_war)

### Interactive Mode

```bash
uv run triangulate interactive
```

Features:
- Natural language topic input
- Iterative query refinement
- Real-time AI analysis

### Background Monitoring

```bash
uv run triangulate monitor --start --topics ./topics.yaml --interval 30m
```

**topics.yaml:**
```yaml
topics:
  - query: "Gaza ceasefire"
    conflict: gaza_war
    max_articles: 20
  - query: "Ukraine aid packages"
    conflict: ukraine_war
    max_articles: 30
```

## Output Formats

### JSON Export

Complete structured data for programmatic consumption:

```json
{
  "metadata": {
    "topic": "Gaza ceasefire negotiations",
    "conflict": "gaza_war",
    "queried_at": "2024-01-15T10:00:00Z",
    "sources_used": ["Reuters", "Al Jazeera", "BBC"],
    "articles_fetched": 45,
    "articles_processed": 38
  },
  "articles": [...],
  "narratives": [...],
  "parties": [...],
  "timeline": [...]
}
```

### Markdown Export

Human-readable report with:
- Executive summary
- Key findings (confirmed facts vs contested claims)
- Party perspectives
- Timeline
- Sources analyzed

## Architecture

### New Modules

**`src/ai/topic_analyzer.py`**
- `detect_conflict()`: AI-powered conflict detection
- `generate_search_queries()`: AI-powered query generation
- `prioritize_sources()`: Source relevance scoring
- `extract_date_range()`: Date range extraction

**`src/ingester/topic_fetcher.py`**
- `TopicFetcher`: Main class for topic-based article fetching
- `fetch_articles_by_topic()`: Orchestrates the complete fetching process
- `_load_sources()`: Loads media sources from `/data/{conflict}/`
- `_fetch_from_sources()`: Fetches from RSS feeds
- `_score_articles()`: Scores articles by relevance

**`src/exporter/`**
- `json_exporter.py`: JSON export functionality
- `markdown_exporter.py`: Markdown report generation

**`src/cli/commands/topic.py`**
- CLI commands for topic-based retrieval

### Data Flow

```
User Query → TopicAnalyzer
    ↓
1. Detect Conflict (Gaza/Ukraine/Iran)
2. Generate Search Queries
3. Prioritize Sources
    ↓
TopicFetcher
    ↓
4. Load Sources from /data/{conflict}/
5. Fetch RSS Feeds
6. Score Articles by Relevance
    ↓
AI Workflow
    ↓
7. Extract Claims
8. Cluster Narratives
9. Classify Parties
10. Assign Verification Status
    ↓
Exporters
    ↓
11. Generate JSON
12. Generate Markdown
```

## Testing

### Unit Tests

26 unit tests covering:
- Topic analyzer functionality
- Topic fetcher operations
- JSON export structure
- Markdown export format

```bash
uv run pytest tests/test_topic_analyzer.py \
  tests/test_topic_fetcher.py \
  tests/test_json_exporter.py \
  tests/test_markdown_exporter.py -v
```

### Integration Tests

9 integration tests validating end-to-end workflows:

```bash
uv run pytest tests/integration/ -v
```

## Implementation Details

### Conflict Detection

Uses LLM with specialized prompt to analyze topic and determine conflict context:

**Prompt Template:**
```
Analyze the topic and determine which conflict context it relates to.

Available conflicts:
- gaza_war: Gaza War, Israel-Hamas conflict
- ukraine_war: Russia-Ukraine war
- iran_war: Iran-related conflicts

Topic: {topic}

Return ONLY the conflict folder name.
```

### Query Generation

Generates 5-10 relevant search queries using AI:

**Considerations:**
- Different keywords and phrases
- Key parties/entities involved
- Various aspects and perspectives
- Balance source diversity

### Relevance Scoring

Each article is scored 0-1 based on semantic similarity:

**Scoring Criteria:**
- 0.9-1.0: Highly relevant - directly about the topic
- 0.7-0.9: Very relevant - closely related
- 0.5-0.7: Moderately relevant - tangentially related
- 0.3-0.5: Somewhat relevant - mentions but not focus
- 0.0-0.3: Not relevant - unrelated

Default threshold: 0.3 (configurable)

## Configuration

Requires `LLM_API_KEY` environment variable for full functionality.

```bash
export LLM_API_KEY="your-api-key"
```

## Error Handling

The system gracefully handles errors:
- LLM failures → Rule-based fallbacks
- RSS feed failures → Skip to next source
- Malformed JSON → Fallback to simple formats
- Missing sources → Continue with available sources

## Future Enhancements

Potential improvements:
- Background daemon for scheduled monitoring
- Real-time alerting for breaking news
- Web interface for interactive exploration
- Advanced filtering options
- Custom conflict folders
- Multi-language support

## See Also

- [Integration Tests README](../../tests/integration/README.md)
- [Main README](../../README.md)
- [Architecture Documentation](../../CLAUDE.md)
