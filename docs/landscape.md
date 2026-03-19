# Project Landscape

## Executive Summary

Triangulate is a Python-first investigation workflow for building topic-oriented cases from news coverage, AI analysis, and linked evidence. It uses multi-agent AI with LangGraph to distinguish verified facts from unverified claims, with a focus on testing how multiple biased agents frame context differently.

## Multi-Agent AI Frameworks (2026)

### LangGraph
Leading open-source framework for building complex, stateful workflows. By modeling verification as a state machine, LangGraph allows specialized agents to collaborate on claim extraction, evidence retrieval, and bias analysis. Preferred for fine-grained state management and ability to handle cyclic workflows.

### CrewAI / Microsoft AutoGen (AG2)
Used for role-based autonomous collaboration. Suitable for scenarios where agents have distinct personas and need to coordinate on verification tasks.

### Core Architecture Patterns
- **Modular agent pod design**: Orchestrated via LangGraph's supervisor or swarm patterns
- **Scout Agents**: Crawl 100+ sources, ranking claims by virality and priority
- **Verifier Agents**: Decompose claims using parsers like T5 and query vector databases (FAISS)
- **Multimodal Agents**: Use Vision Transformer (ViT) for image verification and Conformer ASR for audio checks
- **Observability**: MLflow (v3.0+) and TruLens provide tracing and audit capabilities

### Claim Verification Workflow
1. **Claim Extraction**: Identifying factual assertions from unstructured text
2. **Dynamic Retrieval**: Agents use tools like Serper or Google Search to gather real-time data
3. **Source Credibility Assessment**: Information categorized into tiers to weight evidence
4. **Numerical Verification**: Specialized tools perform mathematical calculations to debunk false data points

### Bias Detection Trends (2026)
- Focus on **transparency** rather than binary true/false labels
- **Confusion matrices** to measure systematic differences across user groups
- Interactive tools showing editorial choices and differential topic emphasis
- Hallucination monitoring metrics for agentic output trustworthiness

---

## Open Source Projects

### Claim Verification & Fact-Checking

| Project | Focus | Notes |
|---------|-------|-------|
| **OpenFactCheck** | Unified framework integrating multiple fact-checking tools (Factcheck GPT, RARR, FacTool) | Includes "Fact-Checker's Arena" leaderboard |
| **Loki** | End-to-end claim verification from long texts | Dissects texts into claims, generates evidence queries |
| **VERIFAID** | FAISS vector similarity search for fact-checking | High-speed similarity searches across large datasets |
| **Fact2Fiction** (AAAI-2026) | Adversarial poisoning attacks on agentic fact-checking | Identifies vulnerabilities in fact-checking pipelines |

### Note on OpenClaw
OpenClaw (210k+ stars) is a **multimodal AI gateway** focused on local AI with capabilities for news, claims, images, and video verification across languages. It is a general-purpose AI verification tool, not a topic-based investigative workflow. Different category from Triangulate.

### News Aggregation & Clustering

| Project | Focus |
|---------|-------|
| **IntellWeave** | Production-scale platform for ingesting web content, verifying claims, serving personalized news feeds |
| **AWS News Clustering** | Event-based clustering using generative AI to group related stories |

### Clustering Techniques
- **HDBSCAN clustering** and **MinHash LSH deduplication** for transforming news streams into chronological timelines
- Semantic embeddings for narrative grouping

---

## OSINT Tools for Investigation

### Source Discovery & Link Analysis

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **Maltego** | Source triangulation, link analysis, entity relationship mapping | Visualize hidden networks, shell company structures |
| **SpiderFoot** | Queries 200+ data sources (social media, WHOIS, DNS, etc.) | Automated source discovery for topics |
| **theHarvester** | Reconnaissance - emails, subdomains, employee names from public sources | Surface associated entities |

### Content & Media Verification

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **TinEye** | Reverse image search using neural networks | Find original source of images, detect alterations |
| **ExifTool** | Extract metadata from files (timestamps, GPS, device details) | Verify authenticity of photo/video evidence |
| **Google Fact Check Explorer** | Search existing fact-checks from reputable organizations | Cross-reference claims |

### Archiving & Evidence Preservation

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **Hunchly** | Automatic web archiving with timestamps and digital signatures | Preserve evidence even if original content deleted |

### Geospatial Verification

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **Google Earth Pro** | Match visual clues in videos/photos with satellite imagery | Verify location-based claims |

### Social Media & Cross-Platform

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **Sherlock** | Search 400+ social media platforms by username | Track entity presence across platforms |
| **Babel X** | Multilingual analysis across 200+ languages | Monitor emerging narratives on surface/dark web |

### Document Analysis

| Tool | Purpose | Integration Potential |
|------|---------|----------------------|
| **Pinpoint** (Google) | Analyze up to 200,000 files with OCR, transcription | Process large document collections for investigations |

### Frameworks & Directories

- **OSINT Framework**: Categorized directory of hundreds of specialized tools
- **Bellingcat's Toolkit**: Community-driven resources for geolocation and social media verification

---

## Triangulate's Unique Position

| Capability | Description |
|------------|-------------|
| **Topic-Based Investigation** | Unlike single-claim verification tools, Triangulate builds comprehensive cases around topics |
| **Multi-Agent with LangGraph** | Specifically designed to study how biased agents frame context differently |
| **Party/Entity Tracking** | Adversarial party analysis with position tracking |
| **Narrative Clustering** | Groups claims into narratives with verification spectrum (CONFIRMED → DEBUNKED) |
| **Evidence Linking** | First-class evidence objects linked to cases |
| **CLI-First Workflow** | Programmatic investigation with `fetch-topic`, `cases`, `ingest`, `monitor` commands |
| **Existing Web UI** | React-based dashboard with review workflow for human oversight |

---

## Competitive Differentiation

1. **Research Platform**: Triangulate is designed as a multi-agent AI research testbed, not just a production fact-checker
2. **Topic Scope**: Works on complex, multi-faceted investigations vs. single claim checks
3. **Party-Centric**: Tracks adversarial relationships and entity positions over time
4. **Verification Spectrum**: Uses nuanced status flow (CONFIRMED → PROBABLE → ALLEGED → CONTESTED → DEBUNKED)
5. **Exception-Driven Review**: Human oversight through an exception queue model

---

## References

- LangGraph State Machine Verification: [gurusup.com](https://gurusup.com/blog/best-multi-agent-frameworks-2026)
- Solana-Based Agent Networks for Journalism: [preprints.org](https://www.preprints.org/manuscript/202603.0706/v1/download)
- Multi-Agent AI Systems: [medium.com/codex](https://medium.com/codex/your-chatbot-is-lonely-multi-agent-ai-is-the-future-of-how-software-actually-thinks-4613029438a9)
- OSINT Tools: [Talkwalker](https://www.talkwalker.com/blog/best-osint-tools), [Wiz Academy](https://wiz.io/academy/threat-intel/osint-tools)
- OpenFactCheck: [GitHub/yuxiaw](https://github.com/yuxiaw/OpenFactCheck)
- Fact2Fiction: [GitHub/TrustworthyComp](https://github.com/TrustworthyComp/Fact2Fiction)
