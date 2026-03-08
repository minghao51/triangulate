# Triangulate

**Truth in Timeline.**
A chronological visualization platform that distinguishes verified facts from unverified claims, powered by multi-agent AI and grounded in OSINT verification methodology.

![Status](https://img.shields.io/badge/status-MVP%20Alpha-orange)
![License](https://img.shields.io/badge/license-MIT-blue)
![Stack](https://img.shields.io/badge/stack-Python%20%7C%20SQLite%20%7C%20LangGraph%20%7C%20CLI-green)

---

## 📖 Overview

In the age of information overload, distinguishing **what happened** from **what people say happened** is increasingly difficult. **Triangulate** is a tool designed to visualize world events chronologically while explicitly encoding **epistemological uncertainty**.

Unlike standard news timelines that treat all reports equally, Triangulate separates:
1.  **Verified Facts** (Sensor data, corroborated reports)
2.  **Perspectives/Claims** (Government statements, social media rumors)
3.  **Evidence** (Archived links, hashes, metadata)

Inspired by the verification methodologies of the **International Crisis Group (ICG)** and **Bellingcat**, this project aims to provide a transparent, auditable record of historical events where uncertainty is visible, not hidden.

---

## ✨ Key Features

- **🔍 AI-Powered Topic Retrieval:** NEW - Intelligent search and analysis of news by topic with automatic conflict detection, query generation, and relevance scoring
- **📅 Chronological Visualization:** Interactive timeline (Vis.js) showing events linearly with clustering for high-density periods.
- **✅ Verification Status:** Clear visual encoding for `CONFIRMED`, `PROBABLE`, `ALLEGED`, `CONTESTED`, and `DEBUNKED`.
- **🤖 Dynamic AI Clustering:** Multi-agent AI system that automatically groups sources by narrative stance (e.g., "Official Sources" vs. "Eyewitnesses") rather than hardcoded bias.
- **⚖️ Multi-Party Analysis:** Adversarial investigation where multiple party agents analyze claims from different perspectives, with an arbiter making objective determinations
- **🔒 Local-First Architecture:** All data (media, database, archives) stored locally by default. Cloud APIs used only for AI reasoning (with PII scrubbing).
- **🔗 Evidence Chain:** Every claim is linked to archived evidence (WARC, screenshots) with SHA-256 integrity hashing.
- **👤 Human-in-the-Loop:** AI drafts events; human analysts verify before publication. No AI auto-publishing.

---

## 🏗️ Architecture

Triangulate uses a **Hybrid Local-Cloud** architecture. Data sovereignty remains local, while intelligence is leveraged from hosted SOTA models.

```mermaid
graph TD
    subgraph Local_Host ["Local Host (Docker)"]
        FE[React Frontend]
        BE[Node.js API]
        AI[Python AI Service]
        DB[(PostgreSQL)]
        FS[Local File System]
        AB[ArchiveBox]
        PII[Presidio Scrubber]
    end

    subgraph Cloud ["Cloud Intelligence"]
        LLM[Hosted LLMs (Gemini/Qwen)]
    end

    FE --> BE
    BE --> DB
    BE --> FS
    BE --> AI
    AI --> PII
    PII -- Scrubbed Text --> LLM
    LLM -- Analysis --> AI
    AI --> BE
    BE --> AB
```

### Core Principles
1.  **Data Sovereignty:** Raw media and archives stay on your machine (`./data`).
2.  **Privacy:** PII (names, locations) is scrubbed locally before sending text to Cloud LLMs.
3.  **Abstraction:** Storage and LLM providers are interchangeable via interface layers (ready for S3/Cloud migration).

---

## 🧠 AI Methodology

The AI system is not a single model but a **LangGraph workflow** of specialized agents:

| Agent | Role | Model Preference |
| :--- | :--- | :--- |
| **🕵️ Collector** | Ingests RSS/APIs, extracts claims & metadata. | Fast/Cheap (e.g., Qwen-72B) |
| **🧠 Clusterer** | **Bias Mitigation.** Groups sources by narrative similarity, not pre-defined labels. | High Reasoning (e.g., Gemini 1.5 Pro) |
| **🗣️ Narrator** | Summarizes each cluster's stance independently. | High Reasoning |
| **⚖️ Arbitrator** | Identifies contradictions between clusters & suggests verification steps. | High Reasoning |
| **👤 Human** | **Final Gate.** Reviews AI output, approves, edits, or rejects. | **You** |

---

## 🛠️ Tech Stack (MVP)

| Component | Technology | Notes |
| :--- | :--- | :--- |
| **Interface** | Python CLI (Typer + Rich) | Command-line workflow |
| **AI Service** | Python, LangGraph | Multi-agent orchestration |
| **LLM Interface** | LiteLLM | Gemini, Qwen support |
| **Database** | SQLite | Local storage |
| **RSS Parsing** | feedparser | RSS feed ingestion |
| **HTTP Client** | httpx | API requests |
| **Testing** | pytest | Unit and integration tests |

### Planned (Full Version)
| Component | Technology |
| :--- | :--- |
| **Frontend** | React, TypeScript, Vis.js |
| **Backend** | Node.js, NestJS |
| **Database** | PostgreSQL (TimescaleDB) |
| **Storage** | S3-compatible |
| **Archiving** | ArchiveBox |
| **Privacy** | Microsoft Presidio |

---

## 🚀 Getting Started (MVP)

### Prerequisites
- Python 3.11+
- uv (Python package manager)
- API Key for LLM provider (Gemini or Qwen)

### Installation

1. **Clone the Repository**
   ```bash
   git clone https://github.com/yourusername/triangulate.git
   cd triangulate
   ```

2. **Install Dependencies**
   ```bash
   uv sync --all-extras
   ```

3. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your LLM_API_KEY
   ```

4. **Initialize Database**
   ```bash
   uv run triangulate init-db
   ```

### Usage

The MVP provides a CLI interface for the complete verification workflow:

```bash
# Ingest content from RSS feeds
uv run triangulate ingest

# Process content with AI agents
uv run triangulate process

# Review pending events interactively
uv run triangulate review

# Query the timeline
uv run triangulate query --days 7

# Run complete pipeline
uv run triangulate run-pipeline

# 🆕 Topic-Based News Retrieval (NEW)
# Fetch and analyze news by topic using AI
uv run triangulate fetch-topic "Gaza ceasefire negotiations"

# Interactive topic exploration
uv run triangulate interactive

# Background monitoring service
uv run triangulate monitor --start --topics ./topics.yaml
```

#### Topic-Based Retrieval

The new `fetch-topic` command enables intelligent, AI-powered retrieval and analysis of news articles by topic:

**Features:**
- **Automatic conflict detection** (Gaza, Ukraine, Iran)
- **AI-generated search queries** (5-10 relevant queries per topic)
- **Source prioritization** by relevance to topic
- **Article relevance scoring** (filters low-relevance content)
- **Multi-party analysis** through existing AI workflow
- **Structured export** (JSON + Markdown)

**Example:**
```bash
uv run triangulate fetch-topic "Gaza ceasefire negotiations" \
  --output ./results \
  --max-articles 50 \
  --relevance-threshold 0.4
```

**Output:**
- `./results/topic_analysis.json` - Complete structured data
- `./results/topic_report.md` - Human-readable summary
- `./results/metadata.json` - Query and processing metadata

See [docs/20260308-topic-based-retrieval.md](docs/20260308-topic-based-retrieval.md) for detailed documentation.

### Verification Workflow
1. **Ingest:** Fetch articles from configured RSS/API sources
2. **Process:** AI extracts claims, clusters narratives, assigns verification status
3. **Review:** Human reviews events via CLI (approve/reject/edit)
4. **Query:** Explore the verified timeline

### Configuration

Edit `config.toml` to configure:
- RSS feed URLs
- LLM model and parameters
- Database path
- Logging settings

Example:
```toml
[sources.rss]
bbc = "https://feeds.bbci.co.uk/news/rss.xml"
reuters = "https://www.reutersagency.feed.com/rss/"

[ai]
model = "gemini/gemini-2.0-flash-exp"
temperature = 0.3
```

---

## 📅 Roadmap

### MVP (Current)
- [x] **Phase 1: Project Setup** (Python, uv, dependencies)
- [x] **Phase 2: Database Layer** (SQLite, SQLAlchemy models)
- [x] **Phase 3: Content Ingestion** (RSS feeds, NewsAPI)
- [x] **Phase 4: AI Agent System** (Collector, Clusterer, Narrator, Classifier)
- [x] **Phase 5: CLI Interface** (ingest, process, review, query commands)
- [x] **Phase 6: Testing** (unit tests, fixtures)
- [x] **Phase 7: Party-Based Analysis** (multi-party adversarial workflow)
- [x] **Phase 8: Topic-Based Retrieval** (AI-powered topic search & analysis)
  - [x] Conflict detection
  - [x] Query generation
  - [x] Source prioritization
  - [x] Relevance scoring
  - [x] Structured export (JSON + Markdown)

### Full Version (Planned)
- [ ] **Phase 9: Web Frontend** (React timeline visualization)
- [ ] **Phase 10: Evidence Pipeline** (ArchiveBox integration, SHA-256 hashing)
- [ ] **Phase 11: Privacy Layer** (Presidio PII scrubbing)
- [ ] **Phase 12: Production Database** (PostgreSQL + TimescaleDB)
- [ ] **Phase 13: Cloud Migration** (S3 storage, managed infrastructure)

---

## ⚠️ Disclaimers & Ethics

1.  **Not Legal Advice:** This tool aggregates public information. It is not a legal record.
2.  **Hallucination Risk:** AI models may generate incorrect summaries. **All AI output must be human-verified before publication.**
3.  **Bias Mitigation:** Dynamic clustering reduces hardcoded bias but does not eliminate it. Users should review source groups critically.
4.  **Privacy:** Do not upload sensitive personal data (PII) to cloud LLMs. The local scrubber is a safeguard, not a guarantee.
5.  **Archival Rights:** Respect website Terms of Service when archiving content.

---

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting PRs.

**Areas needing help:**
- 🎨 Frontend Visualization (D3.js enhancements)
- 🛡️ Security (Enhanced PII scrubbing)
- 🤖 Prompt Engineering (Improving Clusterer accuracy)

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.