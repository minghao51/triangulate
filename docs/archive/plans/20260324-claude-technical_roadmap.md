# Triangulate Phase II — Technical Roadmap
*Multi-Agent Investigation & Bias Analysis Framework*

---

## 0. Preamble & Guiding Principles

This roadmap supersedes the Phase II proposal. It preserves its structural intent while resolving several under-specified decisions that would otherwise become blockers mid-build. Four principles govern every trade-off below:

1. **Local-first, Docker-native.** All tooling must run cleanly on a single developer machine. No cloud dependency on the critical path.
2. **Quality signal before feature expansion.** The evaluation pipeline is not a Phase 4 afterthought — it ships alongside the agent layer so output quality is measurable from day one.
3. **One language for the AI layer.** Python owns all orchestration and inference. No secondary language (Go, TS) is introduced without a concrete, benchmarked justification.
4. **Taxonomy as code.** The bias taxonomy is a versioned config file in the repo, not embedded prompt text. It evolves through PRs, not prompt rewrites.

---

## 1. Current State & Gap Analysis

| Area | Current State | Gap |
|---|---|---|
| Orchestration | Linear, operator-triggered | No agent debate, critique, or self-correction loop |
| Bias handling | Implicit in base LLM | No taxonomy, no labeling, no per-claim audit trail |
| Data layer | Case-level SQLite | No claim-level or entity-level granularity for agent consumption |
| Frontend | Read-only `/api/cases*` | No streaming, no HITL interaction, no operator overrides |
| Quality assurance | None | No neutrality score, no factual consistency check, no regression detection |
| Entity relationships | Not modeled | Contradictions across sources are invisible |

---

## 2. Architecture Decision Record (ADR)

These decisions are locked before Phase 1 begins. Revisiting them mid-build is expensive.

### ADR-1: Orchestration Framework — Custom State Machine over LangGraph

**Decision:** Build a thin, custom orchestration layer using a directed acyclic graph (DAG) with typed edges. Do not adopt LangGraph, LlamaIndex, or CrewAI as a primary dependency.

**Rationale:** LangGraph is powerful but introduces significant abstraction overhead for a three-agent system. A custom layer means: no framework upgrade surprises, full visibility into state transitions, and no hidden prompt injection from framework internals. If the agent count grows beyond five, revisit this decision.

**Implementation sketch:**

```python
# Each agent emits a typed Pydantic model. The orchestrator routes based on state.
class OrchestratorState(BaseModel):
    case_id: str
    status: Literal["ingesting", "researching", "critiquing", "synthesizing", "awaiting_operator", "complete"]
    researcher_output: ResearcherOutput | None = None
    critic_output: CriticOutput | None = None
    synthesizer_output: SynthesizerOutput | None = None
    confidence: float | None = None
    hitl_notes: str | None = None
```

The orchestrator is a pure function: `(OrchestratorState, AgentOutput) -> OrchestratorState`. This makes it trivially testable and serialisable to SQLite for resumability.

### ADR-2: Database — SQLite Now, Postgres Gate at HITL

**Decision:** Stay on SQLite through Phase 2. Migrate to Postgres at the start of Phase 3 (HITL), not "if bottlenecks appear."

**Rationale:** HITL means concurrent writes by definition — the operator and active agents will write to the same case simultaneously. SQLite's write lock will cause silent queueing that is hard to debug under WebSocket pressure. Setting the migration gate at the *start* of Phase 3, not *during* it, avoids a mid-sprint database swap.

**Migration strategy:** Use SQLAlchemy with a database-agnostic dialect from Phase 1. The only Phase 3 change is the connection string and a single Alembic migration run.

### ADR-3: Evaluation Language — Python, Not Go

**Decision:** The evaluation pipeline is Python + `asyncio` + `httpx`. Go is not introduced.

**Rationale:** The eval bottleneck is I/O latency waiting on LLM API responses. Go's concurrency advantage over Python's `asyncio` is negligible in this case — both saturate available API rate limits in the same wall-clock time. Go would add a second language, a second build system, and onboarding friction for no measurable gain. If raw throughput benchmarks ever justify it, this decision can be revisited with data.

### ADR-4: Model Access — OpenRouter as Abstraction Layer

**Decision:** All LLM calls route through OpenRouter. No direct provider SDK imports in agent code.

**Rationale:** Decouples model selection from agent logic. Swapping `claude-3-5-sonnet` for `gpt-4o` for the Critic requires a config change, not a code change. This also enables per-agent model selection (e.g., cheaper model for the Researcher's entity extraction, stronger model for the Synthesizer's reconciliation).

---

## 3. The Bias Taxonomy (Owned Specification)

The Critic agent is only as good as the taxonomy it operates against. This must be a first-class artifact — a versioned YAML file committed to the repo, loaded at agent runtime.

### Taxonomy Schema

```yaml
# bias_taxonomy.yaml — version controlled, loaded by CriticAgent at runtime
version: "1.0.0"
categories:
  - id: loaded_language
    label: "Loaded Language"
    description: "Word choice that carries implicit emotional valence beyond its denotative meaning."
    severity: medium
    signal_patterns:
      - "regime"
      - "radical"
      - "allegedly" # when used selectively for one party
      - "claims" # vs 'says' or 'states'
    mitigation_prompt: |
      Identify any loaded terms in this claim. For each, suggest a neutral alternative
      and explain the valence shift. Output as a list of {term, neutral_alternative, valence_direction}.

  - id: omission_bias
    label: "Omission / Selective Framing"
    description: "Relevant context, counterarguments, or affected parties are absent from the coverage."
    severity: high
    signal_patterns: [] # LLM-detected, no lexical signals
    mitigation_prompt: |
      What relevant facts, stakeholders, or counterarguments are absent from this claim
      that would be expected in neutral coverage of this topic?

  - id: false_balance
    label: "False Balance"
    description: "Equal weight given to positions with unequal evidentiary support."
    severity: medium
    signal_patterns:
      - "both sides"
      - "some say"
      - "others argue"
    mitigation_prompt: |
      Does this claim present equivalent weight to positions with non-equivalent evidence?
      Identify any asymmetry between the evidence cited for each position.

  - id: source_framing
    label: "Source Selection Bias"
    description: "Overreliance on sources with known ideological alignment or institutional interests."
    severity: low
    signal_patterns: []
    mitigation_prompt: |
      Evaluate the sourcing pattern in this article. Are cited sources predominantly
      from one ideological direction, one industry, or one government body?

  - id: headline_body_mismatch
    label: "Headline–Body Mismatch"
    description: "The headline implies a claim that the body text does not support."
    severity: high
    signal_patterns: []
    mitigation_prompt: |
      Compare the headline claim to the evidentiary support in the body text.
      Rate the degree of mismatch on a scale of 0-3 and explain.
```

**Governance:** Taxonomy changes are PR-reviewed. The `version` field is bumped on any category add, remove, or `mitigation_prompt` change. The evaluation pipeline records which taxonomy version was active at the time of each case generation — this enables apples-to-apples comparison in pairwise ranking.

**Baseline reference:** The initial taxonomy above is custom-authored. For future expansion, cross-reference MBFC (Media Bias Fact Check) category labels and the Reuters Institute's framing taxonomy as external validation sources, but do not import them as-is — they are designed for human raters, not LLM prompts.

---

## 4. Agent Architecture & Inter-Agent Protocols

### Agent Roster

| Agent | Responsibility | Input | Output Model |
|---|---|---|---|
| **Researcher** | Extracts claims, maps entities, scores source diversity | Raw article batch | `ResearcherOutput` |
| **Critic** | Evaluates claims against bias taxonomy | `ResearcherOutput` + taxonomy | `CriticOutput` |
| **Synthesizer** | Reconciles discrepancies, produces neutral case draft | Both outputs above | `SynthesizerOutput` |
| **Orchestrator** | Routes state, triggers HITL pauses, manages confidence gates | All agent outputs | `OrchestratorState` |

### Pydantic Contracts (Inter-Agent Protocol)

All inter-agent data is typed. No agent receives raw strings from another agent.

```python
class Claim(BaseModel):
    text: str
    source_url: str
    source_name: str
    entities: list[str]
    confidence: float  # 0.0–1.0, Researcher's self-assessed reliability

class ResearcherOutput(BaseModel):
    case_id: str
    claims: list[Claim]
    entity_map: dict[str, list[str]]  # entity -> list of source URLs mentioning it
    source_diversity_score: float     # 0.0 = echo chamber, 1.0 = maximally diverse

class BiasFlag(BaseModel):
    claim_text: str
    category_id: str          # references taxonomy category id
    severity: Literal["low", "medium", "high"]
    explanation: str
    neutral_alternative: str | None

class CriticOutput(BaseModel):
    case_id: str
    taxonomy_version: str
    flags: list[BiasFlag]
    overall_bias_score: float  # 0.0 = neutral, 1.0 = maximally biased
    flagged_claim_count: int

class Contradiction(BaseModel):
    claim_a: Claim
    claim_b: Claim
    contradiction_description: str
    resolution: str | None          # None if unresolvable, triggers HITL

class SynthesizerOutput(BaseModel):
    case_id: str
    neutral_summary: str
    contradictions: list[Contradiction]
    unresolved_count: int
    confidence: float               # below threshold triggers HITL
    sources_used: list[str]
```

### Agent Communication Flow

```
Ingestion Daemon
      │
      ▼
 Researcher ──────────────────────────────────────┐
      │ ResearcherOutput                           │
      ▼                                            │
   Critic ◄── bias_taxonomy.yaml                  │
      │ CriticOutput                               │
      ▼                                            │
 Synthesizer ◄──────────────────────────────────── ┘
      │ SynthesizerOutput
      ▼
 Orchestrator
      │
      ├── confidence >= threshold ──► Mark COMPLETE ──► Eval Pipeline
      │
      └── confidence < threshold ───► Mark AWAITING_OPERATOR
                                            │
                                            ▼
                                      HITL Workbench (Phase 3)
                                            │
                                            ▼
                                    Operator injects context
                                            │
                                            ▼
                                   Re-run Synthesizer only
```

**Anti-looping guard:** The Synthesizer may only be re-run a maximum of `MAX_SYNTHESIZER_RETRIES` (default: 2) times per case, configurable via environment variable. After the limit, the case is locked to `AWAITING_OPERATOR` regardless of confidence score. This prevents runaway LLM spend.

---

## 5. Revised Phase Plan

The original proposal's phase ordering placed the evaluation pipeline last. This roadmap moves it forward — an eval harness ships with Phase 2, so the multi-agent refactor ships with a quality signal attached, not into a void.

---

### Phase 1 — Ingestion & Schema Modernization
**Goal:** Automate the pipeline and structure data for agent consumption.
**Effort:** 2–3 weeks
**Owner lock-in:** ADR-2 (SQLAlchemy abstraction) must be implemented here, not retrofitted later.

**Actions:**

- Build the ingestion daemon with connectors for RSS, NewsAPI, and direct HTML scraping (use `feedparser`, `httpx`, `trafilatura` for extraction)
- Implement micro-batching for relevance triage: batch up to 20 headlines/summaries in a single LLM call before deciding which warrant full-text processing
- Extend the SQLite schema to support claim-level and entity-level rows (not just case-level blobs)
- Wrap all DB access in SQLAlchemy — no raw SQLite calls anywhere in application code

**New schema (additive, non-breaking):**
```sql
CREATE TABLE claims (
    id TEXT PRIMARY KEY,
    case_id TEXT REFERENCES cases(id),
    text TEXT NOT NULL,
    source_url TEXT,
    source_name TEXT,
    confidence REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE entities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT  -- PERSON, ORG, LOCATION, EVENT
);

CREATE TABLE claim_entities (
    claim_id TEXT REFERENCES claims(id),
    entity_id TEXT REFERENCES entities(id),
    PRIMARY KEY (claim_id, entity_id)
);

CREATE TABLE bias_flags (
    id TEXT PRIMARY KEY,
    claim_id TEXT REFERENCES claims(id),
    category_id TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    severity TEXT NOT NULL,
    explanation TEXT,
    neutral_alternative TEXT
);
```

**Pros:** Immediate cost reduction via micro-batching; richer granularity for Phase 2 agents.
**Cons:** Existing case data requires a one-time migration script; schema is more complex to query ad-hoc.

---

### Phase 2 — Multi-Agent Refactor & Bias Detection
**Goal:** Replace the linear generation pipeline with the three-agent network.
**Effort:** 4–6 weeks

**Actions:**

- Implement `ResearcherAgent`, `CriticAgent`, `SynthesizerAgent` with Pydantic contracts as specified in Section 4
- Implement the `Orchestrator` state machine; serialise `OrchestratorState` to SQLite for resumability across process restarts
- Ship `bias_taxonomy.yaml` v1.0.0; wire `CriticAgent` to load it at runtime
- Add `MAX_SYNTHESIZER_RETRIES` guard and `AWAITING_OPERATOR` state
- Configure per-agent model selection via a config file (e.g., `agents.yaml`)

**Also in Phase 2 (moved forward from original Phase 4):**

- Implement the eval harness as a Python CLI (`uv run eval`) that pulls `COMPLETE` cases and scores them. This does not need to be feature-complete — a single `NeutralityScore` metric from an LLM-as-judge is enough to establish a baseline before Phase 3 ships.
- Record `taxonomy_version` on every `CriticOutput` so future pairwise comparisons are version-aware.

**Pros:** Modular agent design; eval harness means Phase 3 ships with quality already measurable.
**Cons:** Higher latency per case (3 LLM calls minimum); orchestration logic requires careful testing to prevent state corruption.

---

### Phase 3 — Database Migration & HITL Workbench
**Goal:** Migrate to Postgres; transform the frontend into an interactive operational platform.
**Effort:** 4–6 weeks

**Backend changes:**

- Swap SQLite connection string for Postgres (Alembic migration; this is the *only* database code change if Phase 1's SQLAlchemy abstraction was done correctly)
- Migrate FastAPI to support Server-Sent Events (SSE) for streaming agent thought logs
- Add HITL endpoints: `POST /api/cases/{id}/override`, `POST /api/cases/{id}/approve`, `POST /api/cases/{id}/inject-context`
- The `inject-context` endpoint accepts operator text, appends it to `OrchestratorState.hitl_notes`, and triggers a Synthesizer re-run (subject to `MAX_SYNTHESIZER_RETRIES`)

**Frontend — HITL Workbench layout:**

The UI is redesigned as a three-pane workbench. This intentionally discards the current read-only dashboard.

```
┌─────────────────────────────────────────────────────────────┐
│  TRIANGULATE WORKBENCH                        [Active Cases] │
├───────────────────┬──────────────────┬───────────────────────┤
│  SOURCE PANE      │  ENTITY PANE     │  AGENT PANE           │
│                   │                  │                        │
│  Article list     │  Entity graph    │  Streaming agent log   │
│  with bias flags  │  (D3 or simple   │  (SSE-fed, newest      │
│  inline           │  adjacency list) │  first)                │
│                   │                  │                        │
│  Click article →  │  Contradictions  │  ┌──────────────────┐ │
│  highlight claims │  highlighted     │  │ Confidence: 0.34 │ │
│  in entity pane   │  in red          │  │ Status: AWAITING │ │
│                   │                  │  └──────────────────┘ │
│                   │                  │                        │
│                   │                  │  [Inject context...]   │
│                   │                  │  [Approve] [Reject]    │
└───────────────────┴──────────────────┴───────────────────────┘
```

**HITL interaction model — Checkpoint, not Chat:**

Phase 3 implements the *checkpoint model* only. Agents run to a confidence gate, pause, and surface the case to the operator. The operator reads the agent log, injects context or overrides via a form, and unblocks the case. This is SSE-based (server pushes agent log tokens to the client) — not a bidirectional WebSocket chat. The chat model (operator injecting mid-run, agent adapting in real-time) is a Phase 4+ consideration, once the simpler checkpoint model is validated.

**State management:** Use Zustand (lightweight, no boilerplate) for the React client. The SSE stream updates case state in the store; the three panes subscribe to their relevant slices.

**Pros:** Transforms the tool from dashboard to operational platform; checkpoint model is significantly simpler to build correctly than real-time chat.
**Cons:** Full frontend rewrite; Postgres migration adds ops overhead (even locally, a `docker-compose.yml` with a Postgres service is required).

---

### Phase 4 — Evaluation Pipeline (Full Build)
**Goal:** Expand the Phase 2 eval harness into a complete quality and regression system.
**Effort:** 2–3 weeks

**Actions:**

- Expand the eval CLI with all three metrics: `NeutralityScore`, `EvidenceLinkage`, `FactualConsistency`
- Implement pairwise ranking: given two versions of the same case (e.g., before and after a prompt change), ask the judge model "which is more neutral and better evidenced?" Record win rates over time.
- Store eval results in a dedicated `eval_runs` table with foreign keys to `cases` and the `taxonomy_version` active at generation time
- Add a simple eval dashboard tab to the Workbench (a time-series chart of average neutrality score and a table of recent pairwise results)
- Eval runs are async — they never block case generation. Schedule them via a background task triggered by the `COMPLETE` status transition.

**Judge model prompt skeleton:**

```
You are a neutral editorial judge evaluating the quality of an AI-generated investigative case summary.

Evaluate the following case on three dimensions:
1. Neutrality (0–10): Does the summary avoid loaded language, false balance, and selective framing?
2. Evidence Linkage (0–10): Are all factual claims traceable to a cited source?
3. Factual Consistency (0–10): Are there internal contradictions within the summary?

Return ONLY a JSON object: {"neutrality": N, "evidence_linkage": N, "factual_consistency": N, "notes": "..."}

Case to evaluate:
{case_content}
```

**Pairwise prompt skeleton:**

```
You are comparing two versions of the same investigative case summary.
Which version is more neutral, better evidenced, and more internally consistent?

Version A: {case_a}
Version B: {case_b}

Return ONLY: {"winner": "A" | "B" | "tie", "reason": "..."}
```

**Pros:** Concrete regression prevention; pairwise ranking sidesteps the "what is a 7/10" calibration problem.
**Cons:** Recurring token cost per eval run; judge model's own biases affect the scores (mitigate by using the same judge model consistently across all runs).

---

## 6. Recommended Stack (Local Dev)

| Layer | Choice | Notes |
|---|---|---|
| Python env | `uv` | As-is |
| Web framework | FastAPI | Add SSE support in Phase 3 |
| ORM | SQLAlchemy 2.x | Async-capable; enables DB swap in Phase 3 |
| Database (P1–P2) | SQLite | Via SQLAlchemy |
| Database (P3+) | Postgres | `docker-compose.yml` service; Alembic migration |
| LLM access | OpenRouter | All agents; per-agent model config |
| Agent contracts | Pydantic v2 | Strict mode enabled |
| Frontend | Vite + React | Zustand for state; SSE via native `EventSource` |
| Containerisation | Docker Compose | One command local start for all services |
| Eval | Python + `asyncio` + `httpx` | No Go; revisit if benchmark justifies |
| Ingestion | `feedparser`, `trafilatura`, `httpx` | Pure Python |

---

## 7. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent looping burns token budget | Medium | High | `MAX_SYNTHESIZER_RETRIES` guard + per-case spend cap via OpenRouter |
| Bias taxonomy drifts without governance | High | Medium | PR-review gate on `bias_taxonomy.yaml`; version recorded on every eval run |
| SQLite write contention surfaces earlier than expected | Low | Medium | SQLAlchemy abstraction means early migration is cheap |
| LLM judge model inconsistency degrades eval signal | Medium | Medium | Pin judge model version in eval config; never auto-upgrade it |
| Phase 3 frontend rewrite scope expands | High | Medium | Strict checkpoint-model-only scope for P3; chat model explicitly deferred |
| Pydantic schema changes break agent handoffs | Medium | High | Version agent contracts; write contract-level unit tests before Phase 2 ships |

---

## 8. Open Questions (Decisions Deferred)

These are intentionally not decided in this roadmap. They should each be resolved before the relevant phase begins.

1. **Entity graph visualisation in Phase 3:** D3 force-directed graph vs. a simpler adjacency list table. D3 is powerful but adds significant frontend complexity. Decide at Phase 3 kickoff based on how rich the entity data actually is at that point.
2. **Contradiction resolution UI:** Should the operator's HITL context injection be free-form text, or a structured form (e.g., "select which claim is correct")? Free-form is faster to build; structured produces cleaner training data if the system is ever fine-tuned.
3. **Multi-operator support:** Is this single-user local tooling, or does it need operator accounts and case assignment? This determines whether Postgres's row-level security is needed.
4. **Taxonomy expansion process:** Who has merge rights on `bias_taxonomy.yaml`? Should category additions require a minimum number of case examples demonstrating the gap?
