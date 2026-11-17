# Triangulate Project Enhancement Roadmap

## Multi-Agent Non-Bias News Platform with Intelligent Ingestion and Human-in-the-Loop Evaluation

**Document Version:** 1.0
**Date:** March 24, 2026
**Author:** Technical Architecture Team

---

## Executive Summary

This technical document outlines a comprehensive roadmap for enhancing the Triangulate project from its current state as a Python-first investigation workflow to a full-featured multi-agent non-bias news platform. The proposed enhancements address five critical domains: automated news ingestion, multi-agent bias detection, agentic workflow orchestration, human-in-the-loop collaboration, and robust evaluation pipelines. Each phase is designed with clear deliverables, effort estimates, and trade-off analyses to support informed decision-making.

The current Triangulate implementation provides a solid foundation with its CLI-driven workflow, FastAPI layer, and React frontend. However, significant gaps exist in automated news ingestion, real-time bias analysis, sophisticated multi-agent coordination, human oversight mechanisms, and systematic evaluation frameworks. This roadmap proposes a phased approach that balances rapid value delivery with long-term architectural integrity.

---

## 1. Current State Analysis

### 1.1 Existing Architecture Overview

The Triangulate project currently operates as a local Python application with the following core components:

**Backend Infrastructure:**
- **CLI Layer** (`src/cli/`): Typer-based operator-facing commands for ingest, fetch-topic, case review, and monitor runs
- **Case Orchestration** (`src/cases/`): Orchestration boundary and read model construction
- **HTTP API** (`src/http/`): FastAPI application exposing read-only endpoints for case data
- **Storage Layer** (`src/storage/`): SQLite-backed persistence with migrations
- **AI Module** (`src/ai/`): Contains agents, topic analyzer, geocoder, schemas, tracing utilities, and workflow orchestration

**Frontend Infrastructure:**
- **React Application** (`frontend/`): TypeScript-based UI consuming read-only `/api/cases*` endpoints
- **Component Structure**: Pages, components, services, stores, and type definitions

**Current Workflow:**
The system follows a topic-based retrieval pattern where users initiate investigations through CLI commands. The `fetch-topic` command accepts a topic query, detects conflict domains, generates search queries, fetches candidate articles, scores relevance, and produces investigation outputs. The monitor command enables recurring pipeline execution based on YAML topic configurations.

### 1.2 Identified Gaps and Limitations

#### Gap 1: Manual News Ingestion Process

The current system requires manual topic initiation through CLI commands. While the `fetch-topic` workflow provides basic article retrieval, it lacks automated RSS feed monitoring, real-time news API integration, and intelligent source discovery. Users must manually specify topics and cannot benefit from continuous monitoring of diverse news sources without active intervention. The ingestion pipeline does not support deduplication across sources, content quality filtering, or automatic topic clustering.

#### Gap 2: Limited Multi-Agent Coordination

Although the `src/ai/agents/` directory exists, the current implementation lacks sophisticated multi-agent orchestration. The system does not implement specialized agents for distinct tasks such as source credibility assessment, bias detection, fact verification, and narrative analysis. There is no agent communication protocol, no task delegation mechanism, and no consensus-building framework among agents. The AI workflow appears centralized rather than distributed across cooperative agents with specialized capabilities.

#### Gap 3: Absent Bias Detection Framework

The project description mentions "distinguishing verified facts from unverified claims" and "OSINT verification methodology," but the current codebase lacks explicit bias detection mechanisms. There is no implementation for detecting political leaning, emotional framing, selection bias, confirmation bias, or source reliability scoring. The system does not provide bias indicators, comparative analysis across sources, or transparency metrics for users to understand potential slant in coverage.

#### Gap 4: Missing Human-in-the-Loop Mechanisms

The current architecture enforces a strict boundary where the frontend is read-only and all mutations occur through CLI commands. While this separation provides operational control, it creates a significant gap in human oversight during the analysis process. There are no interfaces for human reviewers to validate agent decisions, correct misclassifications, provide feedback on bias assessments, or guide investigation directions. The system lacks annotation tools, review queues, and expert input integration points.

#### Gap 5: No Evaluation Pipeline

The project does not implement systematic evaluation mechanisms for measuring agent accuracy, bias detection effectiveness, or news quality assessment. There are no benchmarking tools, ground truth datasets, or performance metrics dashboards. The system cannot track improvement over time, compare model performance, or validate the reliability of its outputs. This absence of evaluation infrastructure limits the ability to iterate and improve the platform systematically.

#### Gap 6: Basic Frontend Limitations

The React frontend serves primarily as a presentation layer with case index and detail tabs. It lacks interactive visualization of bias metrics, timeline comparisons across sources, credibility dashboards, and collaborative review interfaces. The user experience does not support drill-down into agent reasoning, evidence chains, or confidence intervals. Modern news analysis platforms require rich visualizations that communicate complex information intuitively.

---

## 2. Proposed Enhancement Roadmap

### Phase 1: Automated News Ingestion Pipeline (8-12 weeks)

#### Objective
Establish a robust, automated news ingestion system that continuously monitors diverse sources, extracts structured content, and populates the investigation pipeline without manual intervention.

#### Technical Specifications

**2.1.1 Multi-Source RSS Feed Aggregator**

The ingestion layer should implement a feed management system capable of handling hundreds of RSS/Atom feeds concurrently. Each feed requires configuration for polling frequency, content extraction rules, and reliability scoring. The system should maintain a feed registry that tracks publication schedules, historical reliability, and source categorization.

```python
# Proposed Feed Registry Schema
class FeedSource(BaseModel):
    id: str
    name: str
    url: str
    category: NewsCategory  # politics, technology, world, business, etc.
    credibility_tier: int  # 1-5 tier system
    polling_interval_minutes: int
    last_fetched: datetime
    consecutive_failures: int
    is_active: bool
    bias_annotation: Optional[BiasLabel]  # left, center-left, center, center-right, right
```

**2.1.2 News API Integration Layer**

Beyond RSS feeds, the system should integrate with commercial news APIs for broader coverage:

| API Provider | Coverage | Rate Limits | Cost Model | Recommended Use |
|-------------|----------|-------------|------------|-----------------|
| NewsAPI.org | 70K+ sources | 100-500 requests/day (free) | $449/month (business) | Breaking news, headlines |
| Webz.io | News archive + blogs | Custom | Enterprise pricing | Historical analysis |
| GDELT Project | Global monitoring | Free API | Free | Event detection, sentiment |
| MediaCloud | 100K+ sources | Research access | Free (research) | Academic analysis |
| NewsData.io | 50K+ sources | 200 requests/day (free) | $150/month (starter) | Budget-friendly option |

**2.1.3 Content Extraction and Normalization**

Each ingested article must undergo content extraction and normalization:

1. **Full-Text Extraction**: Use libraries like `trafilatura`, `newspaper3k`, or `readability-lxml` for article body extraction
2. **Metadata Extraction**: Parse publication date, author, source, category, and tags
3. **Content Cleaning**: Remove boilerplate, advertisements, and navigation elements
4. **Language Detection**: Implement `langdetect` or `fasttext` for language identification
5. **Entity Extraction**: Named entity recognition for people, organizations, and locations
6. **Deduplication**: Fuzzy matching using SimHash or MinHash for near-duplicate detection

**2.1.4 Article Queue and Processing Pipeline**

Implement a message queue architecture for scalable article processing:

```
[Feed Fetcher] -> [Raw Article Queue] -> [Content Extractor] -> [Processed Article Queue] -> [Analysis Pipeline]
                            |                                      |
                    [Dead Letter Queue]              [Deduplication Check]
```

Recommended technologies:
- **Redis Streams** or **RabbitMQ** for message queuing
- **Celery** or **Dramatiq** for task distribution
- **PostgreSQL** for persistent article storage (upgrade from SQLite)

#### Implementation Options

**Option A: Extend Current Python Stack (Recommended)**
- **Description**: Build ingestion pipeline within existing Python codebase using Celery + Redis
- **Effort**: 6-8 weeks
- **Pros**: Minimal architectural changes, leverages existing patterns, Python ecosystem maturity
- **Cons**: Single-language constraint, limited horizontal scaling compared to distributed systems

**Option B: Microservices Architecture**
- **Description**: Separate ingestion as independent services with API communication
- **Effort**: 10-12 weeks
- **Pros**: Independent scaling, technology flexibility, fault isolation
- **Cons**: Increased operational complexity, inter-service communication overhead, higher infrastructure costs

**Option C: Serverless Functions**
- **Description**: Deploy ingestion functions on AWS Lambda, GCP Cloud Functions, or Azure Functions
- **Effort**: 8-10 weeks
- **Pros**: Pay-per-use pricing, automatic scaling, reduced operational burden
- **Cons**: Cold start latency, vendor lock-in, debugging complexity, limited control over execution environment

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Feed Registry Service | CRUD operations for RSS feed management | 1 week |
| Feed Poller Worker | Scheduled RSS feed fetching with error handling | 2 weeks |
| Content Extraction Pipeline | Article parsing, cleaning, and normalization | 2 weeks |
| Deduplication Service | Near-duplicate detection and canonical article selection | 1 week |
| Article Storage Migration | SQLite to PostgreSQL migration for scale | 1 week |
| News API Connectors | Integration with 2-3 commercial news APIs | 2 weeks |
| Monitoring Dashboard | Ingestion metrics, feed health, queue status | 1 week |
| Testing and Documentation | Unit tests, integration tests, API documentation | 2 weeks |

#### Success Metrics

- Ingestion latency < 5 minutes from publication to database
- 95% feed availability (handle failures gracefully)
- Deduplication accuracy > 98% (minimize false positives/negatives)
- Support for 500+ concurrent RSS feeds

---

### Phase 2: Multi-Agent Architecture (10-14 weeks)

#### Objective
Transform the AI module into a sophisticated multi-agent system with specialized agents for news analysis tasks, orchestrated through a coordination layer with consensus mechanisms.

#### Technical Specifications

**2.2.1 Agent Taxonomy**

Design specialized agents with distinct responsibilities:

| Agent Type | Responsibility | Output | Dependencies |
|------------|---------------|--------|--------------|
| **Ingestion Agent** | Monitor sources, fetch content, queue articles | Article metadata, raw content | Feed Registry |
| **Credibility Agent** | Assess source reliability, track record | Credibility score (0-100), trust indicators | Historical data |
| **Bias Detection Agent** | Identify political leaning, framing, sentiment | Bias vector, confidence score | NLP models, labeled data |
| **Fact Extraction Agent** | Extract claims, entities, relationships | Structured claims, entity graph | NER, relation extraction |
| **Verification Agent** | Cross-reference claims with known facts | Verification status, evidence links | Fact databases, OSINT |
| **Narrative Agent** | Identify story arcs, timeline construction | Narrative structure, key events | Temporal reasoning |
| **Synthesis Agent** | Combine agent outputs into investigation report | Final analysis, recommendations | All agent outputs |
| **Orchestrator Agent** | Coordinate task distribution, resolve conflicts | Task assignments, consensus decisions | Agent registry |

**2.2.2 Agent Communication Protocol**

Implement a structured inter-agent communication system:

```python
# Agent Message Schema
class AgentMessage(BaseModel):
    message_id: str
    timestamp: datetime
    source_agent: AgentType
    target_agent: Optional[AgentType]  # None for broadcast
    message_type: MessageType  # request, response, notification, consensus
    payload: Dict[str, Any]
    confidence: float  # 0.0 to 1.0
    requires_response: bool
    correlation_id: Optional[str]  # For request-response chains
```

**2.2.3 Consensus Mechanisms**

For tasks requiring multiple agent perspectives, implement consensus algorithms:

1. **Weighted Voting**: Each agent votes with confidence-weighted influence
2. **Evidence Accumulation**: Combine evidence from multiple agents with source credibility weighting
3. **Deviation Detection**: Flag significant disagreements for human review
4. **Bayesian Aggregation**: Update belief distributions based on agent inputs

**2.2.4 Agent Framework Options**

**Option A: Custom Agent Framework (Recommended for Control)**
- **Description**: Build lightweight agent framework on top of existing `src/ai/` structure
- **Technology**: Python asyncio, Pydantic for schemas, Redis for message passing
- **Effort**: 6-8 weeks
- **Pros**: Full control, tailored to news analysis domain, no external dependencies
- **Cons**: Development overhead, must build all tooling

**Option B: LangGraph Integration**
- **Description**: Use LangGraph for stateful multi-agent workflows
- **Technology**: LangGraph, LangChain, LangSmith for observability
- **Effort**: 4-6 weeks
- **Pros**: Mature framework, built-in state management, visualization tools
- **Cons**: Learning curve, potential vendor lock-in, abstraction overhead

**Option C: CrewAI Framework**
- **Description**: Implement agents using CrewAI's role-playing paradigm
- **Technology**: CrewAI, LangChain backend
- **Effort**: 3-5 weeks
- **Pros**: Rapid development, intuitive role-based design, built-in task delegation
- **Cons**: Less control over agent internals, newer framework with fewer production examples

**Option D: AutoGen Integration**
- **Description**: Microsoft AutoGen for multi-agent conversations
- **Technology**: AutoGen, Azure integrations
- **Effort**: 5-7 weeks
- **Pros**: Research-backed, strong conversation patterns, Microsoft ecosystem
- **Cons**: Heavier framework, conversation-focused (less task-oriented)

#### Agent Implementation Priority

| Priority | Agent | Rationale | Dependencies |
|----------|-------|-----------|--------------|
| P0 | Orchestrator Agent | Central coordination required first | None |
| P0 | Bias Detection Agent | Core differentiator feature | NLP models |
| P1 | Credibility Agent | Essential for bias context | Historical data |
| P1 | Fact Extraction Agent | Required for verification | NER models |
| P2 | Verification Agent | Enhances reliability | Fact databases |
| P2 | Narrative Agent | Advanced analysis | All P0/P1 agents |
| P3 | Synthesis Agent | Output generation | All agents |

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Agent Base Classes | Abstract base agent with communication protocol | 1 week |
| Orchestrator Agent | Task distribution and consensus logic | 2 weeks |
| Bias Detection Agent | Multi-dimensional bias analysis | 3 weeks |
| Credibility Agent | Source reliability assessment | 2 weeks |
| Fact Extraction Agent | Claim and entity extraction | 2 weeks |
| Inter-Agent Communication | Message bus, routing, serialization | 2 weeks |
| Consensus Framework | Voting, evidence aggregation, conflict resolution | 2 weeks |
| Agent Observability | Logging, tracing, performance metrics | 1 week |
| Testing Suite | Agent unit tests, integration tests, mocks | 2 weeks |

#### Success Metrics

- Agent response time < 30 seconds per article analysis
- Inter-rater agreement (Fleiss' Kappa) > 0.6 among bias-detecting agents
- 90% task completion rate without human intervention
- Consensus convergence within 3 agent rounds for 95% of cases

---

### Phase 3: Bias Detection System (8-12 weeks)

#### Objective
Implement a comprehensive bias detection framework that analyzes news articles across multiple bias dimensions and provides transparent, explainable assessments.

#### Technical Specifications

**2.3.1 Multi-Dimensional Bias Taxonomy**

Move beyond binary "biased/unbiased" classification to a nuanced multi-dimensional analysis:

| Bias Dimension | Description | Detection Approach |
|---------------|-------------|-------------------|
| **Political Leaning** | Left-right spectrum position | Lexicon analysis, source patterns, stance detection |
| **Emotional Framing** | Use of loaded language, sentiment manipulation | Sentiment analysis, emotional lexicon, framing detection |
| **Selection Bias** | What facts are included/excluded | Claim coverage comparison across sources |
| **Source Bias** | Reliability and track record of cited sources | Source credibility scoring, citation analysis |
| **Presentation Bias** | How information is structured and emphasized | Structure analysis, prominence detection |
| **Confirmation Bias** | Seeking evidence that supports predetermined conclusions | Argument structure analysis, counter-argument detection |
| **Omission Bias** | Critical context missing | Knowledge graph completeness check |
| **Narrative Bias** | Story framing that shapes perception | Narrative arc analysis, protagonist/antagonist identification |

**2.3.2 Bias Detection Pipeline**

```
Article Input
    |
    v
[Preprocessing Layer] -> Tokenization, entity extraction, sentence segmentation
    |
    v
[Feature Extraction Layer] -> TF-IDF, embeddings, stylistic features, citation patterns
    |
    v
[Model Ensemble Layer] -> Multiple bias classifiers with confidence scores
    |
    v
[Aggregation Layer] -> Weighted combination based on model reliability
    |
    v
[Explanation Layer] -> Generate human-readable bias rationale
    |
    v
Bias Report Output
```

**2.3.3 Model Architecture**

**Option A: Fine-tuned Transformer Models (Recommended)**
- **Description**: Fine-tune BERT/RoBERTa models on bias-labeled datasets
- **Datasets**: BABE (Bias Annotations By Experts), Media Bias Corpus, AllSides dataset
- **Effort**: 4-6 weeks for training + validation
- **Pros**: State-of-the-art accuracy, transfer learning benefits, well-understood architecture
- **Cons**: Requires GPU for training, model size considerations

**Option B: Hybrid NLP + ML Approach**
- **Description**: Combine traditional NLP features with gradient boosting classifiers
- **Components**: TF-IDF vectors, sentiment scores, lexicon matches, stylistic features + XGBoost
- **Effort**: 3-4 weeks
- **Pros**: Faster inference, interpretable features, lower resource requirements
- **Cons**: Lower accuracy for nuanced bias, manual feature engineering

**Option C: LLM-Based Analysis**
- **Description**: Use GPT-4, Claude, or similar LLMs for bias assessment with structured prompts
- **Effort**: 2-3 weeks for prompt engineering
- **Pros**: Nuanced understanding, easy to iterate, explainable outputs
- **Cons**: Higher cost per article, latency concerns, API dependency

**Option D: Ensemble of Multiple Approaches**
- **Description**: Combine transformer, traditional ML, and LLM outputs
- **Effort**: 6-8 weeks
- **Pros**: Best accuracy, robust to individual model failures
- **Cons**: Complexity, maintenance overhead, higher computational cost

#### Bias Ground Truth Data

| Dataset | Size | Annotations | Access |
|---------|------|-------------|--------|
| BABE | 3,700 sentences | Expert bias labels | Free |
| Media Bias Corpus | 3,000 articles | Multi-dimensional bias | Research access |
| AllSides Headlines | 40K+ headlines | Political leaning | Free (rate-limited) |
| News Bias Benchmark | 10K articles | Bias type labels | Request access |
| SemEval Task 4 | 300 news articles | Propaganda detection | Free |

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Bias Taxonomy Schema | Data models for multi-dimensional bias | 1 week |
| Feature Extraction Pipeline | NLP feature computation | 2 weeks |
| Bias Classification Models | Train/fine-tune bias detectors | 3 weeks |
| Model Evaluation Framework | Accuracy, precision, recall, F1 metrics | 1 week |
| Bias Explanation Generator | Human-readable bias rationales | 2 weeks |
| Source Credibility Scorer | Historical accuracy tracking | 2 weeks |
| Comparative Bias Analysis | Cross-source bias comparison | 1 week |
| API Endpoints | REST endpoints for bias analysis | 1 week |

#### Success Metrics

- Political leaning classification accuracy > 80% (4-class: left, center-left, center-right, right)
- Bias detection F1 score > 0.75
- Explanation quality rating > 4/5 from human evaluators
- Processing time < 5 seconds per article

---

### Phase 4: Human-in-the-Loop Enhancement (6-10 weeks)

#### Objective
Integrate human oversight mechanisms that enable domain experts to validate, correct, and guide the multi-agent analysis process while maintaining audit trails and learning from human feedback.

#### Technical Specifications

**2.4.1 Review Queue System**

Implement a prioritized review queue for human intervention:

```python
class ReviewQueue(BaseModel):
    queue_id: str
    items: List[ReviewItem]

class ReviewItem(BaseModel):
    item_id: str
    article_id: str
    agent_outputs: Dict[AgentType, AgentOutput]
    confidence_score: float  # Low confidence = high priority
    priority: ReviewPriority  # low, medium, high, urgent
    assigned_reviewer: Optional[str]
    review_type: ReviewType  # bias_validation, fact_check, source_verification
    created_at: datetime
    sla_deadline: datetime
    status: ReviewStatus  # pending, assigned, in_progress, completed, escalated
```

**Priority Factors:**
- Low agent confidence score (< 0.6)
- Significant disagreement among agents (variance > threshold)
- Sensitive topic categories (politics, health, finance)
- New sources without established credibility
- User-reported concerns

**2.4.2 Review Interface Components**

| Component | Description | Implementation |
|-----------|-------------|----------------|
| **Article Viewer** | Full article display with highlighting | React component, text annotation |
| **Agent Output Panel** | Show each agent's analysis | Collapsible sections, confidence indicators |
| **Bias Visualization** | Multi-dimensional bias chart | Radar chart, spectrum display |
| **Evidence Browser** | View supporting evidence for claims | Expandable evidence cards |
| **Feedback Form** | Submit corrections and annotations | Structured form, free-text fields |
| **Decision Recorder** | Log human decisions | Immutable audit log |
| **Dispute Resolution** | Handle reviewer disagreements | Escalation workflow |

**2.4.3 Human Feedback Integration**

The system must learn from human corrections:

1. **Immediate Impact**: Flag similar articles for additional scrutiny
2. **Model Retraining Queue**: Aggregate corrections for periodic model updates
3. **Agent Weight Adjustment**: Increase/decrease agent influence based on accuracy
4. **Source Recalibration**: Adjust source credibility based on correction patterns
5. **Bias Threshold Tuning**: Refine sensitivity based on false positive/negative rates

**2.4.4 Collaboration Features**

| Feature | Description | Use Case |
|---------|-------------|----------|
| **Review Assignment** | Assign items to specific reviewers based on expertise | Domain expert routing |
| **Second Opinion** | Request additional reviewer for disputed cases | Quality assurance |
| **Discussion Thread** | Comment system on review items | Team collaboration |
| **Review History** | Past decisions on similar articles | Consistency checking |
| **Expertise Matching** | Match reviewer skills to article topics | Accuracy improvement |

**2.4.5 Implementation Options**

**Option A: Extend Current Frontend (Recommended)**
- **Description**: Add review components to existing React application
- **Technology**: React, TypeScript, shadcn/ui components
- **Effort**: 4-6 weeks
- **Pros**: Consistent UI, leverages existing infrastructure
- **Cons**: May require significant state management changes

**Option B: Dedicated Review Application**
- **Description**: Separate application for review workflow
- **Technology**: Next.js standalone application
- **Effort**: 6-8 weeks
- **Pros**: Focused UX, independent deployment, separate access control
- **Cons**: Duplication of shared components, additional maintenance

**Option C: Integration with Existing Review Tools**
- **Description**: Integrate with Label Studio, Prodigy, or similar annotation tools
- **Technology**: Label Studio backend, custom frontend
- **Effort**: 3-5 weeks
- **Pros**: Proven annotation workflow, active community, export formats
- **Cons**: Less customization, potential workflow mismatch

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Review Queue Service | Backend for queue management | 2 weeks |
| Review Assignment Logic | Priority calculation, expertise matching | 1 week |
| Article Viewer Component | Display with annotation support | 1 week |
| Agent Output Visualization | Show multi-agent analysis | 1 week |
| Feedback Collection Forms | Structured correction input | 1 week |
| Audit Logging Service | Immutable decision records | 1 week |
| Feedback Integration Pipeline | Apply corrections to models | 2 weeks |
| Review Analytics Dashboard | Track review metrics, accuracy | 1 week |

#### Success Metrics

- Review turnaround time < 24 hours for high-priority items
- Human-AI agreement rate > 85%
- Correction implementation rate > 90% (within 1 week)
- Reviewer satisfaction score > 4/5

---

### Phase 5: Evaluation Pipeline (6-8 weeks)

#### Objective
Establish a systematic evaluation framework that measures system performance across all components, enables continuous improvement, and provides transparency for stakeholders.

#### Technical Specifications

**2.5.1 Evaluation Metrics Taxonomy**

| Category | Metric | Description | Target |
|----------|--------|-------------|--------|
| **Ingestion** | Coverage Rate | Percentage of relevant news captured | > 90% |
| **Ingestion** | Latency | Time from publication to ingestion | < 5 min |
| **Ingestion** | Deduplication Accuracy | Precision/recall of duplicate detection | > 95% |
| **Bias Detection** | Political Leaning Accuracy | Classification accuracy | > 80% |
| **Bias Detection** | Bias F1 Score | Overall bias detection quality | > 0.75 |
| **Bias Detection** | Explanation Quality | Human rating of explanations | > 4/5 |
| **Multi-Agent** | Task Completion Rate | Percentage of tasks completed without error | > 95% |
| **Multi-Agent** | Consensus Rate | Percentage of cases reaching consensus | > 90% |
| **Multi-Agent** | Agent Agreement | Inter-rater reliability (Kappa) | > 0.6 |
| **Human-in-Loop** | Review Accuracy | Percentage of human decisions validated | > 90% |
| **Human-in-Loop** | Feedback Implementation Rate | Corrections applied to system | > 85% |
| **Overall** | End-to-End Latency | Total processing time per article | < 2 min |

**2.5.2 Ground Truth Generation**

Create benchmark datasets for evaluation:

1. **Synthetic Dataset**: Generate articles with known bias characteristics
2. **Expert Annotation**: Have domain experts label a sample of real articles
3. **Crowdsourced Labels**: Use platforms like Amazon MTurk for scale
4. **Historical Analysis**: Use articles with established bias from AllSides/Ad Fontes Media
5. **Continuous Feedback Loop**: Ground truth grows from validated human reviews

**2.5.3 Evaluation Pipeline Architecture**

```
[Evaluation Trigger] -> Daily scheduled / On-demand / Post-deployment
        |
        v
[Dataset Selection] -> Random sample / Stratified sample / Edge cases
        |
        v
[Blind Evaluation] -> Run system without ground truth access
        |
        v
[Comparison Engine] -> Compare outputs to ground truth
        |
        v
[Metric Computation] -> Calculate all defined metrics
        |
        v
[Report Generation] -> Dashboard update, alerts, recommendations
        |
        v
[Model Registry Update] -> Version performance metrics
```

**2.5.4 A/B Testing Framework**

Implement controlled experiments for system improvements:

```python
class Experiment(BaseModel):
    experiment_id: str
    name: str
    hypothesis: str
    control_variant: str  # Current production version
    treatment_variant: str  # New version to test
    traffic_split: float  # Percentage for treatment (e.g., 0.2 for 20%)
    start_date: datetime
    end_date: datetime
    success_metrics: List[Metric]
    minimum_detectable_effect: float
    statistical_power: float
    status: ExperimentStatus
```

**2.5.5 Continuous Monitoring**

| Monitoring Type | Description | Alert Threshold |
|-----------------|-------------|-----------------|
| **Performance Drift** | Model accuracy degradation over time | > 5% drop from baseline |
| **Data Drift** | Input distribution changes | Statistical test p < 0.05 |
| **Volume Anomalies** | Unusual ingestion patterns | > 3 standard deviations |
| **Latency Spikes** | Processing time increases | > 2x baseline |
| **Error Rate** | System error frequency | > 1% of requests |
| **Human Override Rate** | Frequency of manual corrections | > 10% of reviews |

**2.5.6 Implementation Options**

**Option A: Custom Evaluation Framework (Recommended)**
- **Description**: Build evaluation pipeline tailored to news analysis
- **Technology**: Python, Pandas, Matplotlib, internal dashboard
- **Effort**: 4-5 weeks
- **Pros**: Full customization, domain-specific metrics
- **Cons**: Development overhead

**Option B: MLflow Integration**
- **Description**: Use MLflow for experiment tracking and model registry
- **Technology**: MLflow, integrated with existing Python backend
- **Effort**: 2-3 weeks
- **Pros**: Industry standard, mature tooling, model versioning
- **Cons**: May need customization for bias-specific metrics

**Option C: Weights & Biases**
- **Description**: Cloud-based experiment tracking and visualization
- **Technology**: W&B SDK, cloud dashboard
- **Effort**: 2-3 weeks
- **Pros**: Excellent visualization, collaboration features, easy setup
- **Cons**: Cloud dependency, cost at scale

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Evaluation Metrics Module | Metric calculation functions | 1 week |
| Ground Truth Dataset | Initial labeled dataset (1000+ articles) | 2 weeks |
| Evaluation Pipeline | Automated evaluation workflow | 2 weeks |
| A/B Testing Framework | Experiment management system | 2 weeks |
| Monitoring Dashboard | Real-time performance visualization | 1 week |
| Alert System | Automated performance alerts | 1 week |
| Evaluation Report Template | Standardized reporting format | 1 week |

#### Success Metrics

- Evaluation pipeline execution time < 30 minutes
- Statistical significance detection for > 95% of A/B tests
- Alert response time < 1 hour for critical issues
- 100% coverage of key metrics in weekly reports

---

### Phase 6: Frontend Redesign (10-16 weeks)

#### Objective
Completely redesign the frontend to provide a modern, interactive user experience that effectively communicates multi-agent analysis, bias metrics, and investigation findings.

#### Technical Specifications

**2.6.1 Information Architecture**

| Section | Description | Key Features |
|---------|-------------|--------------|
| **Dashboard** | Overview of system activity | Ingestion metrics, recent articles, alerts |
| **News Feed** | Browse ingested articles with bias indicators | Filters, sorting, bias visualization |
| **Investigation View** | Deep-dive into specific topics/cases | Timeline, agent outputs, evidence |
| **Bias Explorer** | Compare bias across sources | Side-by-side comparison, spectrum view |
| **Review Center** | Human-in-the-loop interface | Queue, assignment, feedback forms |
| **Analytics** | System performance and trends | Charts, reports, exports |
| **Settings** | Configuration and preferences | Sources, alerts, API access |

**2.6.2 Key UI Components**

**Bias Spectrum Visualization:**
```
                        CENTER
                          |
    LEFT  <-------------| |------------->  RIGHT
           [CNN]   [NYT]   [WSJ]   [Fox]
                    ▲
               Current Article
```

**Multi-Agent Confidence Display:**
```
┌─────────────────────────────────────────────┐
│ Agent Analysis Confidence                    │
├─────────────────────────────────────────────┤
│ Bias Agent     ████████████████░░░░  78%    │
│ Credibility    ████████████████████  95%    │
│ Fact Checker   ██████████░░░░░░░░░░  52%    │
│ Narrative      ████████████████░░░░  82%    │
├─────────────────────────────────────────────┤
│ Consensus: 76% | Status: Moderate Confidence │
└─────────────────────────────────────────────┘
```

**Evidence Chain Visualization:**
```
Claim: "Economic growth exceeded expectations"
         │
         ├── [Reuters] ✓ Primary source
         │      └── Government report citation
         │
         ├── [Bloomberg] ✓ Confirmation
         │      └── Independent analysis
         │
         └── [Opinion Blog] ✗ Not credible
                └── No verifiable source
```

**2.6.3 Technology Stack Options**

**Option A: Next.js 16 + React 19 (Recommended)**
- **Description**: Modern React framework with server components
- **Technology**: Next.js 16, React 19, TypeScript, Tailwind CSS 4, shadcn/ui
- **Effort**: 10-12 weeks
- **Pros**: Latest features, excellent DX, server-side rendering, API routes integrated
- **Cons**: Learning curve for server components, migration from current React app

**Option B: Continue with Current React Stack**
- **Description**: Enhance existing React application incrementally
- **Technology**: React (current version), TypeScript, add state management
- **Effort**: 8-10 weeks
- **Pros**: Less disruption, faster initial delivery
- **Cons**: Technical debt, limited modern features

**Option C: Vue.js / Nuxt.js**
- **Description**: Complete rewrite in Vue ecosystem
- **Technology**: Nuxt 3, Vue 3, TypeScript, Nuxt UI
- **Effort**: 12-14 weeks
- **Pros**: Different paradigm, excellent reactivity
- **Cons**: Team learning curve, ecosystem differences

**2.6.4 Design System**

Establish a comprehensive design system:

| Element | Specification |
|---------|--------------|
| **Color Palette** | Neutral base (grays), semantic colors (bias spectrum), accent colors |
| **Typography** | Primary: Inter/Geist, Secondary: Mono for data |
| **Spacing Scale** | 4px base unit, consistent margins/padding |
| **Components** | Cards, tables, charts, modals, forms, tooltips |
| **Animations** | Subtle transitions, loading states, micro-interactions |
| **Accessibility** | WCAG 2.1 AA compliance, keyboard navigation, screen reader support |

**2.6.5 Performance Requirements**

| Metric | Target |
|--------|--------|
| First Contentful Paint | < 1.5s |
| Largest Contentful Paint | < 2.5s |
| Time to Interactive | < 3s |
| Cumulative Layout Shift | < 0.1 |
| Bundle Size (initial) | < 200KB gzipped |

#### Deliverables

| Deliverable | Description | Effort |
|-------------|-------------|--------|
| Design System | Component library, design tokens | 2 weeks |
| Dashboard Page | System overview with metrics | 1 week |
| News Feed Page | Article browsing with filters | 2 weeks |
| Investigation Detail Page | Multi-agent analysis view | 2 weeks |
| Bias Explorer Page | Source comparison interface | 2 weeks |
| Review Center Page | Human-in-the-loop interface | 2 weeks |
| Analytics Page | Performance dashboards | 1 week |
| API Integration | Connect frontend to enhanced backend | 2 weeks |
| Testing & QA | E2E tests, accessibility audit | 2 weeks |

#### Success Metrics

- Page load time < 3 seconds
- Accessibility score > 90 (Lighthouse)
- User satisfaction > 4/5 (survey)
- Error rate < 0.1%

---

## 3. Implementation Timeline and Dependencies

### 3.1 Phased Rollout Schedule

```
Month 1-3:  Phase 1 - Automated News Ingestion
            ├── Week 1-2: Feed Registry, Database Migration
            ├── Week 3-4: RSS Poller, Content Extraction
            ├── Week 5-6: Deduplication, API Connectors
            └── Week 7-8: Testing, Documentation

Month 2-5:  Phase 2 - Multi-Agent Architecture (Overlapping with Phase 1)
            ├── Week 1-2: Agent Framework, Communication Protocol
            ├── Week 3-4: Orchestrator Agent
            ├── Week 5-8: Bias Detection, Credibility Agents
            └── Week 9-10: Fact Extraction, Integration

Month 4-7:  Phase 3 - Bias Detection System (Overlapping with Phase 2)
            ├── Week 1-2: Bias Taxonomy, Feature Extraction
            ├── Week 3-5: Model Training/Fine-tuning
            ├── Week 6-7: Explanation Generation
            └── Week 8: API Integration

Month 6-8:  Phase 4 - Human-in-the-Loop Enhancement
            ├── Week 1-2: Review Queue Backend
            ├── Week 3-4: Review Interface Components
            ├── Week 5-6: Feedback Integration
            └── Week 7-8: Analytics Dashboard

Month 7-9:  Phase 5 - Evaluation Pipeline (Overlapping with Phase 4)
            ├── Week 1-2: Metrics Module, Ground Truth
            ├── Week 3-4: Evaluation Pipeline, A/B Testing
            └── Week 5-6: Monitoring Dashboard

Month 8-12: Phase 6 - Frontend Redesign
            ├── Week 1-2: Design System
            ├── Week 3-6: Core Pages (Dashboard, Feed, Investigation)
            ├── Week 7-8: Review Center, Analytics
            └── Week 9-10: Testing, Polish
```

### 3.2 Dependency Graph

```
Phase 1 (Ingestion)
    │
    ├──> Phase 2 (Agents) ──> Phase 3 (Bias)
    │         │                    │
    │         └────────────────────┼──> Phase 4 (Human-in-Loop)
    │                              │           │
    │                              │           v
    │                              └──────> Phase 5 (Evaluation)
    │                                          │
    └──────────────────────────────────────────┴──> Phase 6 (Frontend)
```

### 3.3 Resource Requirements

| Phase | Engineering FTE | Duration | External Dependencies |
|-------|-----------------|----------|----------------------|
| Phase 1 | 2-3 | 8-12 weeks | News API subscriptions |
| Phase 2 | 2-3 | 10-14 weeks | LLM API access, GPU for training |
| Phase 3 | 2 | 8-12 weeks | Labeled datasets, GPU for training |
| Phase 4 | 1-2 | 6-10 weeks | None |
| Phase 5 | 1-2 | 6-8 weeks | Annotation tools (optional) |
| Phase 6 | 2-3 | 10-16 weeks | Design tools, hosting |

**Total Estimated Effort:** 48-72 person-weeks over 12-16 months with parallelization

---

## 4. Risk Assessment and Mitigation

### 4.1 Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Model Accuracy Below Target** | Medium | High | Ensemble approach, continuous retraining, human oversight |
| **Scalability Bottlenecks** | Medium | High | Early load testing, horizontal scaling design, caching |
| **Third-Party API Dependency** | High | Medium | Multiple provider fallbacks, caching, graceful degradation |
| **Data Quality Issues** | High | High | Validation pipelines, source credibility scoring, anomaly detection |
| **Integration Complexity** | Medium | Medium | API versioning, comprehensive testing, staged rollout |

### 4.2 Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Resource Constraints** | Medium | High | Prioritized backlog, MVP approach, phased delivery |
| **Scope Creep** | High | Medium | Strict change control, clear phase definitions |
| **Knowledge Concentration** | Medium | High | Documentation, cross-training, pair programming |
| **Stakeholder Alignment** | Low | High | Regular demos, feedback cycles, transparent progress |

### 4.3 Ethical and Legal Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Bias in Bias Detection** | High | Critical | Diverse training data, fairness metrics, external audit |
| **Copyright Infringement** | Medium | High | Content licensing, fair use policy, legal review |
| **Misinformation Amplification** | Low | Critical | Verification systems, confidence thresholds, source vetting |
| **Privacy Violations** | Low | High | Data minimization, retention policies, anonymization |

---

## 5. Budget Considerations

### 5.1 Infrastructure Costs (Monthly Estimates)

| Component | Low Estimate | High Estimate |
|-----------|-------------|---------------|
| Cloud Compute (API servers) | $200 | $500 |
| Database (PostgreSQL managed) | $100 | $300 |
| Redis/Queue Service | $50 | $150 |
| Object Storage (articles, reports) | $50 | $200 |
| LLM API Calls | $500 | $2,000 |
| News API Subscriptions | $300 | $800 |
| Monitoring & Observability | $50 | $150 |
| **Total Monthly** | **$1,250** | **$4,100** |

### 5.2 One-Time Costs

| Item | Estimate |
|------|----------|
| GPU Training (cloud or dedicated) | $500 - $2,000 |
| Labeled Dataset Acquisition | $0 - $5,000 |
| Design Tools/Licenses | $500 - $1,500 |
| Security Audit | $5,000 - $15,000 |
| **Total One-Time** | **$6,000 - $23,500** |

---

## 6. Success Criteria and KPIs

### 6.1 System Performance KPIs

| KPI | Current State | Phase 1 Target | Final Target |
|-----|---------------|----------------|--------------|
| Articles Ingested/Day | 0 (manual) | 1,000+ | 10,000+ |
| Time to Analysis | N/A | < 5 minutes | < 2 minutes |
| Bias Detection Accuracy | N/A | 70% | 85% |
| Human Override Rate | N/A | < 20% | < 10% |
| System Uptime | ~95% | 99% | 99.9% |

### 6.2 Business Value Metrics

| Metric | Measurement Method | Target |
|--------|-------------------|--------|
| Time to Investigation | Track case creation to completion | 50% reduction |
| User Engagement | Session duration, return visits | 3x increase |
| Reviewer Productivity | Articles reviewed per hour | 2x increase |
| Decision Quality | User feedback, correction rates | > 90% accuracy |

---

## 7. Recommendations

### 7.1 Immediate Priorities (Next 30 Days)

1. **Database Migration**: Move from SQLite to PostgreSQL to support scale
2. **Agent Framework Selection**: Evaluate and select multi-agent framework
3. **News API Integration**: Set up at least one commercial news API
4. **Design System Foundation**: Establish UI component library

### 7.2 Strategic Recommendations

1. **Start with Ingestion**: Phase 1 provides immediate value and data for subsequent phases
2. **Iterate on Agents**: Deploy agents incrementally, starting with highest-impact tasks
3. **Invest in Human-in-Loop Early**: Human feedback is essential for model improvement
4. **Build Evaluation from Day 1**: Don't defer metrics and monitoring
5. **Consider Open Source Contributions**: Several components could benefit community

### 7.3 Technology Decisions Summary

| Decision Point | Recommendation | Rationale |
|---------------|----------------|-----------|
| Agent Framework | Custom + LangGraph hybrid | Control + mature orchestration |
| Bias Model | Fine-tuned transformer ensemble | Best accuracy/runtime balance |
| Frontend Framework | Next.js 16 | Modern features, performance, DX |
| Database | PostgreSQL | Scale, features, ecosystem |
| Queue System | Redis Streams | Simplicity, performance, existing patterns |

---

## 8. Conclusion

This roadmap presents a comprehensive plan to transform Triangulate from a CLI-driven investigation tool into a sophisticated multi-agent news analysis platform. The phased approach allows for incremental value delivery while building toward an integrated system with automated ingestion, intelligent bias detection, human oversight, and robust evaluation.

The identified gaps in the current architecture—particularly the absence of automated ingestion, limited multi-agent coordination, missing bias detection, and lack of human-in-the-loop mechanisms—represent significant opportunities for differentiation in the news intelligence space. By addressing these gaps systematically, Triangulate can become a leading platform for transparent, verifiable news analysis.

Success will depend on disciplined execution, continuous evaluation, and responsiveness to user feedback. The modular architecture proposed allows for course corrections as the project evolves, ensuring that the platform remains adaptable to changing requirements and technological advances in the rapidly evolving AI landscape.

---

## Appendix A: Technology Stack Summary

### Backend

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11+ |
| Web Framework | FastAPI | 0.100+ |
| Task Queue | Celery + Redis | Latest |
| Database | PostgreSQL | 15+ |
| ORM | SQLAlchemy | 2.0+ |
| ML Framework | PyTorch / Transformers | Latest |
| LLM Integration | OpenAI / Anthropic API | Latest |

### Frontend

| Component | Technology | Version |
|-----------|------------|---------|
| Framework | Next.js | 16+ |
| UI Library | React | 19+ |
| Language | TypeScript | 5.0+ |
| Styling | Tailwind CSS | 4.0+ |
| Components | shadcn/ui | Latest |
| Charts | Recharts / Visx | Latest |
| State | Zustand | Latest |

### Infrastructure

| Component | Technology | Notes |
|-----------|------------|-------|
| Hosting | AWS / GCP / Azure | TBD |
| Containerization | Docker | All services |
| Orchestration | Kubernetes (optional) | If scale requires |
| CI/CD | GitHub Actions | Current setup |
| Monitoring | Prometheus + Grafana | Recommended |
| Logging | ELK Stack or Loki | Recommended |

---

## Appendix B: Glossary

| Term | Definition |
|------|------------|
| **Agent** | An autonomous AI component with specific responsibilities and capabilities |
| **Bias Vector** | Multi-dimensional representation of article bias across defined axes |
| **Consensus** | Agreement among multiple agents on a particular analysis |
| **Ground Truth** | Verified correct labels used for evaluation |
| **Human-in-the-Loop** | System design that incorporates human oversight and feedback |
| **OSINT** | Open Source Intelligence - information from publicly available sources |
| **RSS Feed** | Really Simple Syndication - web feed format for publishing updates |
| **Source Credibility** | Trustworthiness score for news publications |

---

*Document prepared for the Triangulate project enhancement initiative. For questions or clarifications, contact the project maintainers.*
