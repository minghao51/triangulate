This is a strategic upgrade. Using **Hosted SOTA (State-of-the-Art) Models** (like Gemini 1.5 Pro, Qwen-Max, or Claude 3.5) gives you massive context windows (great for analyzing many articles at once) and higher reasoning capabilities than local 8B models. 

However, **hosted models still hallucinate**. The risk reduction comes from their **consistency** and **reasoning**, not immunity. The **Dynamic Perspective Clustering** is the real game-changer for bias—it prevents you from hardcoding "Government vs. Rebel" and lets the data decide the narrative factions (e.g., "Eyewitnesses vs. Officials" or "Western Media vs. State Media").

Here is the **Regenerated Comprehensive Tech Architecture & Plan**.

---

## 🏗️ 1. Revised High-Level Architecture (Hybrid: Local Data + Cloud Intelligence)

Data stays local (privacy/cost), but "Thinking" happens in the cloud (capability).

```
┌─────────────────────────────────────────────────────────────────┐
│                      LOCAL HOST MACHINE                         │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │   Frontend    │  │   Backend     │  │   AI Service  │       │
│  │  (React)      │  │  (Node.js)    │  │  (Python)     │       │
│  │  Port 3000    │  │  Port 3001    │  │  Port 3002    │       │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘       │
│          │                  │                  │               │
│          └──────────────────┼──────────────────┘               │
│                             │                                   │
│  ┌──────────────────────────┼──────────────────────────┐       │
│  │                      DATA LAYER                     │       │
│  │  ┌───────────────┐  ┌───────┴───────┐  ┌──────────┐ │       │
│  │  │  PostgreSQL   │  │  Local File   │  │  Redis   │ │       │
│  │  │  (Docker)     │  │  System (FS)  │  │  Queue   │ │       │
│  │  │  Port 5432    │  │  ./data/store │  │  Port 6379│ │       │
│  │  └───────────────┘  └───────────────┘  └──────────┘ │       │
│  └───────────────────────────────────────────────────────┘       │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              EXTERNAL TOOLS (Docker Containers)           │  │
│  │  [ArchiveBox] [Meilisearch] [MinIO (Optional)]            │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
                             ▼ (Secure API Calls - Text Only)
┌─────────────────────────────────────────────────────────────────┐
│                     CLOUD LLM PROVIDERS                         │
│  [Google Gemini]  [Alibaba Qwen]  [Anthropic Claude]           │
│  (High Reasoning, Large Context, Paid API)                      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧠 2. The Dynamic Multi-Agent AI System

This is the core logic update. Instead of hardcoded parties, we use **Narrative Clustering**.

### **Agent Workflow (LangGraph)**

| Step | Agent | Role | Input | Output |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **🕵️ Collector** | Ingestion | RSS/API/URLs | List of Raw Text Snippets + Metadata |
| **2** | **🧠 Clusterer** | **Bias Mitigation** | Raw Snippets | **Dynamic Groups** (e.g., "Group A: Official Statements", "Group B: Civilian Reports") |
| **3** | **🗣️ Narrator** | Synthesis | Grouped Snippets | Summary of each Group's claim (Party A View, Party B View...) |
| **4** | **⚖️ Arbitrator** | Fact-Check | All Summaries | Contradiction Map, Confidence Score, Verification Plan |
| **5** | **👤 Human** | Final Gate | Arbitrator Report | **Approve/Reject/Edit** → Publish to Timeline |

### **How Dynamic Clustering Reduces Bias**
*   **Old Way:** You tell AI "Show me Government vs Rebel view." (Forces binary bias).
*   **New Way:** You tell AI "Analyze these 20 sources. Group them by narrative similarity."
    *   *Result:* Sometimes it finds 2 groups. Sometimes 4. Sometimes it finds that **all sources agree** (high confidence). Sometimes it finds **no consensus** (high conflict).
    *   *Benefit:* The structure emerges from the data, not your preconceptions.

### **Party-Based Adversarial Investigation (New - March 2025)**

An advanced multi-agent workflow that goes beyond simple clustering by having parties investigate claims from their own perspectives.

**Workflow:**
```
Article → Collector → Party Classifier → [Parallel Party Investigators] → Arbiter → Final Determinations
                                       ↓
                                   Party A │ Party B │ Party C
                                       ↓
                                  [Party Findings]
                                       ↓
                            Arbiter (Fact vs Allegation + Classification)
```

**Agents:**

| Agent | Role | Output |
| :--- | :--- | :--- |
| **Collector** | Extract claims from article | List of factual claims with metadata |
| **Party Classifier** | Identify parties mentioned | Canonical party names with aliases |
| **Party Investigators** (Parallel) | Each party investigates from their perspective | Claims supported/contested, unique claims, party stance |
| **Arbiter** | Make objective determinations | FACT vs ALLEGATION, verification status (CONFIRMED/PROBABLE/ALLEGED/CONTESTED/DEBUNKED), reasoning |

**Key Innovations:**

1. **Parallel Party Perspective Taking:** Each party investigates claims independently, providing their position on each claim (SUPPORTS, CONTESTS, or NEUTRAL)

2. **Fact vs Allegation Classification:** The Arbiter distinguishes between:
   - **FACTS:** Observable events that occurred (past tense, verifiable)
   - **ALLEGATIONS:** Interpretations, predictions, statements of intent (future tense, subjective)

3. **Five-Tier Verification System:**
   - **CONFIRMED:** Verifiable fact, multiple sources, no disputes
   - **PROBABLE:** Likely true, credible sources, minor disputes
   - **ALLEGED:** Claim made but not verified, or is opinion
   - **CONTESTED:** Factual dispute between credible sources
   - **DEBUNKED:** Proven false

4. **Controversy Scoring:**
   - Calculates party agreement level (HIGH/MEDIUM/LOW/NONE)
   - Controversy score from 0.0 (unanimous) to 1.0 (completely contested)
   - Identifies which parties support or oppose each claim

**Database Schema Updates:**

- **Claim Model:** Added `fact_allegation_type`, `arbiter_reasoning`, `party_positions`, `controversy_score`
- **New Table:** `PartyInvestigation` - stores full investigation results for each party
- **New Enum:** `FactAllegationType` (FACT, ALLEGATION)

**Implementation:**
- `src/ai/agents/fact_allegation_classifier.py` - Fact vs allegation classification
- `src/ai/agents/party_investigator.py` - Party perspective analysis
- `src/ai/agents/arbiter.py` - Final arbitration with reasoning
- `src/ai/workflows/party_investigation_workflow.py` - LangGraph orchestration

---

## 💻 3. Revised Tech Stack (Hybrid)

| Component | Technology | Why This Choice |
| :--- | :--- | :--- |
| **LLM Orchestration** | **LangGraph** | Best for cyclic agent workflows (Cluster → Narrate → Arbitrate → Loop). |
| **LLM Interface** | **LiteLLM** | **Critical.** Unified API for Gemini, Qwen, Claude. Switch models without code changes. |
| **Backend** | **Node.js (NestJS)** | Robust API, handles local file I/O well. |
| **AI Service** | **Python (FastAPI)** | Native support for LangChain/LangGraph. |
| **Database** | **PostgreSQL 15** | Local Docker. Stores event data + AI logs. |
| **Storage** | **Local Filesystem** | `./data/media`. Abstracted for S3 later. |
| **Archiving** | **ArchiveBox** | Local Docker. Saves snapshots before sending text to LLM. |
| **Privacy Layer** | **Presidio (Microsoft)** | **New Addition.** Scans text for PII (names, phones) before sending to Cloud LLM. |

---

## 🗄️ 4. Data Schema Updates (Dynamic Groups)

We need to store the **Dynamic Groups** generated by the AI.

```json
{
  "event_id": "evt_001",
  "status": "HUMAN_REVIEW_REQUIRED",
  "ai_metadata": {
    "model_used": "gemini-1.5-pro",
    "cost_usd": 0.04,
    "narrative_clusters": [
      {
        "cluster_id": "grp_01",
        "label": "Official Government Sources",
        "source_count": 5,
        "narrative_summary": "Claims defensive strike against military target.",
        "confidence": 0.9
      },
      {
        "cluster_id": "grp_02",
        "label": "Local Civilian Eyewitnesses",
        "source_count": 8,
        "narrative_summary": "Reports residential impact and civilian casualties.",
        "confidence": 0.85
      },
      {
        "cluster_id": "grp_03",
        "label": "International NGOs",
        "source_count": 2,
        "narrative_summary": "Calling for independent investigation.",
        "confidence": 0.95
      }
    ],
    "contradictions": [
      {
        "topic": "Casualties",
        "group_a": "grp_01 (0 reported)",
        "group_b": "grp_02 (15+ reported)"
      }
    ]
  },
  "human_review": {
    "decision": "PUBLISH_CONTESTED",
    "notes": "Clusters accurately reflect available data."
  }
}
```

---

## 🛠️ 5. Implementation Plan (Hybrid Local/Cloud)

### **Phase 1: Local Core & Privacy Layer (Weeks 1-4)**
*   **Goal:** Secure local setup ready for cloud API.
*   **Tasks:**
    1.  Setup Docker Compose (Postgres, Redis, ArchiveBox).
    2.  Build Node.js API with **Storage Abstraction** (Local FS interface).
    3.  **Critical:** Implement **Microsoft Presidio** (or simple regex) to scrub PII before any data leaves your machine.
    4.  Build Basic Timeline UI.
*   **Deliverable:** Secure local system where you can manually add events and store media locally.

### **Phase 2: Cloud AI Integration (Weeks 5-8)**
*   **Goal:** Connect Hosted LLMs with Dynamic Clustering.
*   **Tasks:**
    1.  Setup **LiteLLM** proxy (manage API keys centrally).
    2.  Build **Clusterer Agent** (Prompt: "Group these texts by narrative stance").
    3.  Build **Arbitrator Agent** (Prompt: "Find contradictions between groups").
    4.  Implement **Cost Tracking** (Log token usage per event).
    5.  Build **Admin Review Queue** (Show AI clusters → Human approves).
*   **Deliverable:** System ingests news, clusters perspectives automatically, and waits for your approval.

### **Phase 3: Evidence & Verification (Weeks 9-12)**
*   **Goal:** Link AI claims to archived proof.
*   **Tasks:**
    1.  Integrate ArchiveBox into ingestion pipeline.
    2.  Link Archived URLs to specific Narrative Clusters (e.g., "Group 2 claims are supported by [Archive Link]").
    3.  Implement Hashing for local files.
*   **Deliverable:** Full pipeline: News → AI Cluster → Archive Evidence → Human Verify → Timeline.

### **Phase 4: Optimization & Scale (Months 4+)**
*   **Goal:** Reduce costs and improve speed.
*   **Tasks:**
    1.  **Model Routing:** Use cheap model (Qwen-72B) for clustering, expensive model (Gemini Pro) for arbitration.
    2.  **Caching:** If similar event occurs, check DB before calling API.
    3.  **Cloud Migration:** Move Storage to S3 if local disk fills up.

---


## 🚀 7. Immediate Next Step (Configuration)

Since you are using Hosted LLMs, your immediate setup needs to focus on **API Management** and **Privacy**.

1.  **Get API Keys:** Sign up for Google AI Studio (Gemini) and/or Alibaba Cloud (Qwen).
2.  **Setup LiteLLM:** Install `litellm` python package. It allows you to call all providers with the same code syntax.
3.  **Privacy Test:** Write a script that takes a sample news article, runs it through a local PII scrubber, and sends it to the API. Verify the response.

**Would you like me to:**
1.  Write the **Python Code for the Dynamic Clustering Agent** (using LangGraph + LiteLLM)?
2.  Create the **Docker Compose file** with the Privacy/Scrubbing layer included?
3.  Design the **Admin UI Wireframe** for reviewing AI Clusters (drag/drop sources)?

I recommend **#1 (Clustering Agent Code)** as this is the core logic change you requested.