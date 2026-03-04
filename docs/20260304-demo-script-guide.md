# AI Workflow Demo Guide

## Overview

This guide shows two ways to process news articles through the AI workflow to see how claims, narratives, and parties are extracted and analyzed:

1. **CLI Command** (`process-url`) - Built-in command, recommended for most use cases
2. **Demo Script** (`run_workflow_demo.py`) - Standalone script for testing

Both use the same AI workflow and provide the same output format.

---

## Prerequisites

### 1. LLM API Key

You need an LLM API key set in your `.env` file:

```bash
# Copy .env.example to .env
cp .env.example .env

# Edit .env with your API key:
LLM_API_KEY=your_gemini_api_key_here
LLM_PROVIDER=gemini
```

**How to get a Gemini API key:**
1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create a new API key
3. Paste it in your `.env` file

### 2. Dependencies

The script uses these Python packages (already installed):
- `trafilatura` - Article content extraction (primary)
- `beautifulsoup4` - Fallback content extraction
- `httpx` - HTTP client
- `litellm` - LLM API interface

## Demo Script Usage

The demo script is an alternative way to run the workflow without using the CLI command.

### Basic Command

```bash
uv run scripts/run_workflow_demo.py <article_url>
```

### Examples

```bash
# Al Jazeera article
uv run scripts/run_workflow_demo.py "https://www.aljazeera.com/news/2026/3/3/article"

# BBC article
uv run scripts/run_workflow_demo.py "https://www.bbc.com/news/world-12345678"

# Reuters article
uv run scripts/run_workflow_demo.py "https://www.reuters.com/world/europe/article"
```

## What the Script Does

### 1. Article Fetching

The script attempts to extract article content using a two-tier approach:

**Primary: Trafilatura**
- Best for news sites, blogs, academic articles
- Handles complex layouts
- Removes clutter automatically

**Fallback: BeautifulSoup**
- Used if trafilatura fails
- Extracts content from common HTML elements
- More basic but works on simple sites

### 2. AI Processing Pipeline

The article goes through a 4-step AI workflow:

| Step | Agent | Purpose |
|------|-------|---------|
| **1** | **Collector** | Extracts factual claims (who, what, when, where) |
| **2** | **Clusterer** | Groups claims by narrative similarity (TF-IDF + K-means) |
| **3** | **Narrator** | Summarizes each cluster's stance and identifies themes |
| **4** | **Classifier** | Assigns verification status (CONFIRMED/PROBABLE/ALLEGED/CONTESTED) |

### 3. Output Display

The script displays results in three sections:

#### Event Overview
- Title, verification status, source URL

#### Extracted Claims
For each claim:
- Claim text
- Who (entities involved)
- When (timestamp/date)
- Where (location)
- Confidence level (HIGH/MEDIUM/LOW)
- Verification status

#### Narratives
For each narrative cluster:
- Cluster ID
- Number of claims
- Stance summary (what this perspective claims)
- Key themes
- Main entities/parties

#### Summary
- Total claims and narratives
- Overall verification status
- All identified parties/entities

#### Full JSON Output
Complete event data in JSON format for further processing

## Example Output

```
================================================================================
AI WORKFLOW RESULTS
================================================================================

📰 EVENT OVERVIEW
--------------------------------------------------------------------------------
Title:       Iran updates: US bases, embassies attacked as Tehran steps up Gulf strikes
Status:      CONTESTED
Source:      aljazeera.com

📝 EXTRACTED CLAIMS (3 total)
--------------------------------------------------------------------------------

[1] Iran conducted attacks on US bases and embassies as part of stepped-up Gulf strikes
    Who:        Iran, United States
    When:       Tuesday, March 3, 2026
    Where:      Gulf region
    Confidence: LOW
    Status:     ALLEGED

🎭 NARRATIVES (3 total)
--------------------------------------------------------------------------------

[Narrative 1] Cluster ID: 2
    Claims: 1
    Stance: This narrative asserts that Iran has escalated its military actions...
    Themes: Iranian aggression, U.S. military vulnerability, Gulf regional escalation
    Entities (Parties): Iran, United States, U.S. military bases, U.S. embassies, Gulf region

📊 SUMMARY
--------------------------------------------------------------------------------
Total Claims:      3
Total Narratives:  3
Verification:      CONTESTED
Identified Parties: Gulf region, Iran, United States, U.S. military bases, U.S. embassies
```

## Verification Status Levels

| Status | Meaning |
|--------|---------|
| **CONFIRMED** | High confidence claims, multiple sources agree |
| **PROBABLE** | High confidence with single source, or medium confidence with multiple sources |
| **ALLEGED** | Low confidence or single medium source |
| **CONTESTED** | Significant disagreement between narratives |

## Parties/Entities Identification

The system identifies parties in two ways:

1. **Claim-level**: Entities mentioned in each claim (who field)
2. **Narrative-level**: Main entities involved in each narrative perspective

Common entity types:
- Countries (Iran, United States)
- Organizations (military bases, embassies)
- People (officials, eyewitnesses)
- Locations (cities, regions)

## Troubleshooting

### "No LLM_API_KEY found"
- Make sure `.env` file exists in project root
- Verify `LLM_API_KEY` is set correctly

### "Failed to fetch article"
- URL may be behind a paywall
- Site may block automated access
- Try a different article URL

### "No claims extracted"
- Article content may be too short
- LLM may not find factual claims
- Try with a more substantive news article

### "Content length: < 100 characters"
- Liveblog pages often extract poorly
- Try a standard news article instead
- Video/image-heavy content won't work well

## CLI Integration

The system now includes a built-in CLI command for processing articles by URL.

### `process-url` Command

**Basic Usage:**
```bash
uv run python -m src.cli.main process-url <article_url>
```

**Options:**
- `--json` / `-j`: Output JSON instead of pretty print
- `--save` / `-s`: Save result to database
- `--help`: Show help message

**Examples:**

```bash
# Pretty print results
uv run python -m src.cli.main process-url "https://www.aljazeera.com/news/article"

# Output JSON only
uv run python -m src.cli.main process-url "https://www.bbc.com/news/article" --json

# Process and save to database
uv run python -m src.cli.main process-url "https://reuters.com/article" --save

# Combined: JSON output + save
uv run python -m src.cli.main process-url "url" -j -s
```

**Output:**

The command displays:
- Event overview (title, status, source)
- Extracted claims with who/when/where/confidence
- Narrative clusters with stance summaries and themes
- Identified parties/entities
- Full JSON event data

---

## Demo Script (Alternative)

For standalone usage, use the demo script directly:

```bash
uv run scripts/run_workflow_demo.py <article_url>
```

This provides the same functionality as the CLI command but runs as a standalone script.

---

## Enhanced RSS Ingest Pipeline

The RSS feed fetcher (`src/ingester/rss.py`) has been enhanced to automatically use trafilatura + BeautifulSoup fallback for better content extraction.

**How it works:**
1. RSS feed provides article link and basic content
2. If RSS content < 500 characters, automatically fetches full article
3. Uses trafilatura (primary) → BeautifulSoup (fallback)
4. No changes needed to existing `triangulate ingest` command

**Benefits:**
- Better content extraction from RSS feeds
- Works automatically with existing ingest pipeline
- Handles news sites with partial RSS content

---

## Related Files

### CLI & Scripts
- `src/cli/commands/process_url.py` - CLI command implementation
- `scripts/run_workflow_demo.py` - Standalone demo script
- `src/ingester/rss.py` - Enhanced RSS fetcher with trafilatura

### Core Workflow
- `src/ai/workflow.py` - Main workflow orchestration
- `src/ai/agents/collector.py` - Claim extraction
- `src/ai/agents/clusterer.py` - Narrative clustering
- `src/ai/agents/narrator.py` - Narrative generation
- `src/ai/agents/classifier.py` - Verification classification
