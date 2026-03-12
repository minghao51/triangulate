# Dynamic Clustering Agent - Python Implementation

This is the core AI service for **Triangulate**. It uses **LangGraph** for agent orchestration and **LiteLLM** for multi-provider LLM support.

---

## 📁 Project Structure

```
ai-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Environment & LLM config
│   ├── privacy.py           # PII scrubbing (Presidio)
│   ├── models.py            # Pydantic data models
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py          # Base agent class
│   │   ├── collector.py     # Ingestion agent
│   │   ├── clusterer.py     # Dynamic clustering agent
│   │   ├── narrator.py      # Narrative synthesis
│   │   └── arbitrator.py    # Fact-check & contradiction
│   ├── graph/
│   │   ├── __init__.py
│   │   └── workflow.py      # LangGraph state machine
│   └── utils/
│       ├── __init__.py
│       └── llm.py           # LiteLLM wrapper
├── tests/
├── requirements.txt
├── Dockerfile
└── .env.example
```

---

## 📄 1. `requirements.txt`

```txt
fastapi==0.109.0
uvicorn==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
langgraph==0.0.20
langchain==0.1.0
langchain-core==0.1.10
litellm==1.28.0
presidio-analyzer==2.2.32
presidio-anonymizer==2.2.32
spacy==3.7.2
python-dotenv==1.0.0
aiohttp==3.9.1
```

---

## 📄 2. `app/config.py`

```python
"""
Configuration management for AI Service.
Supports multiple LLM providers via LiteLLM.
"""
from pydantic_settings import BaseSettings
from typing import Optional, Dict
import os

class Settings(BaseSettings):
    # LLM Configuration
    LLM_PROVIDER: str = "gemini"  # gemini, qwen, claude, openai
    LLM_MODEL_CLUSTER: str = "gemini/gemini-1.5-pro"  # High reasoning for clustering
    LLM_MODEL_NARRATE: str = "gemini/gemini-1.5-pro"  # High reasoning for narration
    LLM_MODEL_ARBITRATE: str = "gemini/gemini-1.5-pro"  # High reasoning for arbitration
    LLM_MODEL_CHEAP: str = "qwen/qwen-72b-chat"  # Cheap model for simple tasks
    
    # API Keys (set via .env)
    GEMINI_API_KEY: Optional[str] = None
    QWEN_API_KEY: Optional[str] = None
    CLAUDE_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    
    # Privacy
    ENABLE_PII_SCRUB: bool = True
    PII_ENTITIES: list = ["PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "LOCATION", "DATE_TIME"]
    
    # Rate Limiting
    MAX_TOKENS_PER_REQUEST: int = 8000
    REQUEST_TIMEOUT: int = 60
    
    # Cost Tracking
    TRACK_COSTS: bool = True
    MONTHLY_BUDGET_USD: float = 100.0
    
    class Config:
        env_file = ".env"
        case_sensitive = False

settings = Settings()

# LiteLLM configuration
os.environ.setdefault("GEMINI_API_KEY", settings.GEMINI_API_KEY or "")
os.environ.setdefault("QWEN_API_KEY", settings.QWEN_API_KEY or "")
os.environ.setdefault("ANTHROPIC_API_KEY", settings.CLAUDE_API_KEY or "")
os.environ.setdefault("OPENAI_API_KEY", settings.OPENAI_API_KEY or "")
```

---

## 📄 3. `app/models.py`

```python
"""
Pydantic models for AI Agent data flow.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from datetime import datetime
from enum import Enum

class SourceType(str, Enum):
    NEWS_ARTICLE = "news_article"
    SOCIAL_MEDIA = "social_media"
    GOVT_STATEMENT = "govt_statement"
    EYEWITNESS = "eyewitness"
    NGO_REPORT = "ngo_report"
    SENSOR_DATA = "sensor_data"
    OTHER = "other"

class SourceDocument(BaseModel):
    """Individual source document (article, post, statement)"""
    id: str
    url: str
    content: str
    source_type: SourceType
    published_at: datetime
    author: Optional[str] = None
    language: str = "en"
    metadata: Dict = Field(default_factory=dict)

class NarrativeCluster(BaseModel):
    """A group of sources with similar narrative stance"""
    cluster_id: str
    label: str  # Auto-generated label (e.g., "Official Government Sources")
    source_ids: List[str]
    source_count: int
    narrative_summary: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    key_claims: List[str] = Field(default_factory=list)

class Contradiction(BaseModel):
    """Identified contradiction between clusters"""
    topic: str
    cluster_a_id: str
    cluster_a_claim: str
    cluster_b_id: str
    cluster_b_claim: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]

class ArbitrationResult(BaseModel):
    """Output from Arbitrator agent"""
    contradictions: List[Contradiction]
    verification_questions: List[str]
    overall_confidence: float = Field(ge=0.0, le=1.0)
    recommended_status: Literal["CONFIRMED", "PROBABLE", "ALLEGED", "CONTESTED", "DEBUNKED"]
    notes: str

class AIProcessingState(BaseModel):
    """Complete state passed through LangGraph"""
    event_id: str
    raw_sources: List[SourceDocument]
    scrubbed_sources: List[SourceDocument] = Field(default_factory=list)
    clusters: List[NarrativeCluster] = Field(default_factory=list)
    arbitration: Optional[ArbitrationResult] = None
    ai_metadata: Dict = Field(default_factory=dict)
    cost_usd: float = 0.0
    errors: List[str] = Field(default_factory=list)
    status: Literal["PENDING", "PROCESSING", "REVIEW_READY", "ERROR"] = "PENDING"
```

---

## 📄 4. `app/utils/llm.py`

```python
"""
LiteLLM wrapper for unified LLM interface.
"""
import litellm
from litellm import completion
from app.config import settings
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    """Unified LLM client using LiteLLM"""
    
    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.LLM_MODEL_CLUSTER
        self.cost_tracking: Dict[str, float] = {}
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str = "You are a helpful AI assistant.",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        model_override: Optional[str] = None
    ) -> str:
        """Generate text from LLM with cost tracking"""
        try:
            model = model_override or self.model
            
            response = completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=settings.REQUEST_TIMEOUT
            )
            
            # Track costs
            if settings.TRACK_COSTS:
                cost = litellm.completion_cost(completion_response=response)
                self.cost_tracking[model] = self.cost_tracking.get(model, 0) + cost
                logger.info(f"LLM Cost: ${cost:.4f} (Model: {model})")
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"LLM Generation Error: {str(e)}")
            raise

    def get_total_cost(self) -> float:
        """Get total cost for this session"""
        return sum(self.cost_tracking.values())

# Global client instance
llm_client = LLMClient()
```

---

## 📄 5. `app/privacy.py`

```python
"""
PII Scrubbing using Microsoft Presidio.
Runs locally before sending data to cloud LLMs.
"""
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from app.config import settings
from typing import List
import logging

logger = logging.getLogger(__name__)

class PIIScrubber:
    """Local PII scrubbing before cloud API calls"""
    
    def __init__(self):
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.enabled = settings.ENABLE_PII_SCRUB
    
    def scrub_text(self, text: str, entities: Optional[List[str]] = None) -> str:
        """Remove/replace PII from text"""
        if not self.enabled:
            return text
        
        entities = entities or settings.PII_ENTITIES
        
        try:
            # Analyze for PII
            results = self.analyzer.analyze(
                text=text,
                language="en",
                entities=entities
            )
            
            # Anonymize
            anonymized = self.anonymizer.anonymize(
                text=text,
                analyzer_results=results,
                operators={
                    "PERSON": OperatorConfig("replace", {"new_value": "[PERSON]"}),
                    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[PHONE]"}),
                    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL]"}),
                    "LOCATION": OperatorConfig("replace", {"new_value": "[LOCATION]"}),
                    "DATE_TIME": OperatorConfig("replace", {"new_value": "[DATE]"})
                }
            )
            
            if results:
                logger.info(f"Scrubbed {len(results)} PII entities from text")
            
            return anonymized.text
            
        except Exception as e:
            logger.error(f"PII Scrubbing Error: {str(e)}")
            # Fallback: return original text with warning
            return text
    
    def scrub_sources(self, sources: List[dict]) -> List[dict]:
        """Scrub PII from list of source documents"""
        scrubbed = []
        for source in sources:
            scrubbed_source = source.copy()
            scrubbed_source['content'] = self.scrub_text(source.get('content', ''))
            scrubbed_source['author'] = self.scrub_text(source.get('author', '')) if source.get('author') else None
            scrubbed.append(scrubbed_source)
        return scrubbed

# Global instance
pii_scrubber = PIIScrubber()
```

---

## 📄 6. `app/agents/base.py`

```python
"""
Base agent class for all AI agents.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict
from app.utils.llm import LLMClient
import logging

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """Abstract base class for all agents"""
    
    def __init__(self, model_override: str = None):
        self.llm = LLMClient(model_override)
        self.name = self.__class__.__name__
    
    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Define the agent's system prompt"""
        pass
    
    @abstractmethod
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process state and return updated state"""
        pass
    
    async def generate(self, user_prompt: str, temperature: float = 0.3) -> str:
        """Generate response from LLM"""
        return await self.llm.generate(
            prompt=user_prompt,
            system_prompt=self.system_prompt,
            temperature=temperature
        )
    
    def log_action(self, action: str, details: str = ""):
        """Log agent actions"""
        logger.info(f"[{self.name}] {action}: {details}")
```

---

## 📄 7. `app/agents/clusterer.py` ⭐ (CORE AGENT)

```python
"""
Dynamic Clustering Agent.
Groups sources by narrative similarity, NOT hardcoded labels.
This is the bias mitigation layer.
"""
from typing import Dict, Any, List
import json
from app.agents.base import BaseAgent
from app.models import NarrativeCluster, SourceDocument
import uuid

class ClustererAgent(BaseAgent):
    """
    Dynamically clusters sources by narrative stance.
    No pre-defined categories (e.g., "Government vs Rebel").
    Let the data determine the groups.
    """
    
    @property
    def system_prompt(self) -> str:
        return """
You are an unbiased narrative clustering agent. Your task is to analyze multiple 
source documents about the same event and group them by their NARRATIVE STANCE, 
not by source type, language, or region.

IMPORTANT RULES:
1. Do NOT pre-define categories like "Government" or "Opposition". Let the data determine groups.
2. Group sources that make SIMILAR CLAIMS together, even if they're from different regions.
3. If all sources agree, create ONE cluster with high confidence.
4. If sources contradict, create SEPARATE clusters for each contradictory narrative.
5. Label each cluster descriptively based on the actual claims (e.g., "Sources claiming civilian casualties" not "Western Media").
6. A source can only belong to ONE cluster.
7. Return ONLY valid JSON, no markdown, no explanations.

OUTPUT FORMAT:
{
  "clusters": [
    {
      "cluster_id": "unique_id",
      "label": "Descriptive label based on claims",
      "source_ids": ["id1", "id2"],
      "narrative_summary": "What this group claims",
      "confidence_score": 0.0-1.0,
      "key_claims": ["claim1", "claim2"]
    }
  ]
}
"""
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Cluster sources by narrative"""
        self.log_action("Starting clustering", f"{len(state.get('scrubbed_sources', []))} sources")
        
        sources = state.get('scrubbed_sources', [])
        
        if not sources:
            state['errors'].append("No sources to cluster")
            return state
        
        # Prepare sources for prompt
        sources_text = "\n\n---\n\n".join([
            f"ID: {s['id']}\nType: {s.get('source_type', 'unknown')}\nContent: {s.get('content', '')[:1000]}"
            for s in sources
        ])
        
        prompt = f"""
Analyze these {len(sources)} source documents about the same event and cluster them by narrative stance.

SOURCES:
{sources_text}

Return JSON with clusters as specified in system prompt.
"""
        
        try:
            response = await self.generate(prompt, temperature=0.2)
            
            # Parse JSON response
            # Handle potential markdown code blocks
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "").strip()
            elif response.startswith("```"):
                response = response.replace("```", "").strip()
            
            result = json.loads(response)
            
            # Convert to NarrativeCluster objects
            clusters = []
            for cluster_data in result.get('clusters', []):
                cluster = NarrativeCluster(
                    cluster_id=cluster_data.get('cluster_id', str(uuid.uuid4())),
                    label=cluster_data.get('label', 'Unnamed Cluster'),
                    source_ids=cluster_data.get('source_ids', []),
                    source_count=len(cluster_data.get('source_ids', [])),
                    narrative_summary=cluster_data.get('narrative_summary', ''),
                    confidence_score=min(1.0, max(0.0, cluster_data.get('confidence_score', 0.5))),
                    key_claims=cluster_data.get('key_claims', [])
                )
                clusters.append(cluster)
            
            state['clusters'] = clusters
            state['ai_metadata']['cluster_model'] = self.llm.model
            state['ai_metadata']['cluster_cost'] = self.llm.get_total_cost()
            
            self.log_action("Clustering complete", f"{len(clusters)} clusters created")
            
        except json.JSONDecodeError as e:
            state['errors'].append(f"Clusterer JSON Parse Error: {str(e)}")
            self.log_action("Clustering failed", "JSON parse error")
        except Exception as e:
            state['errors'].append(f"Clusterer Error: {str(e)}")
            self.log_action("Clustering failed", str(e))
        
        return state

# Singleton instance
clusterer_agent = ClustererAgent()
```

---

## 📄 8. `app/agents/narrator.py`

```python
"""
Narrator Agent.
Synthesizes each cluster's narrative into a clear summary.
"""
from typing import Dict, Any, List
import json
from app.agents.base import BaseAgent
from app.models import NarrativeCluster

class NarratorAgent(BaseAgent):
    """
    Creates detailed narrative summaries for each cluster.
    """
    
    @property
    def system_prompt(self) -> str:
        return """
You are a narrative synthesis agent. For each cluster of sources, create a clear, 
neutral summary of their claims.

RULES:
1. Be neutral and factual. Do not judge truthfulness.
2. Include specific claims (numbers, dates, locations if available).
3. Note the level of agreement within the cluster.
4. Flag any internal inconsistencies within the cluster.
5. Return ONLY valid JSON.

OUTPUT FORMAT:
{
  "cluster_summaries": [
    {
      "cluster_id": "id",
      "detailed_summary": "Full narrative summary",
      "key_claims": ["claim1", "claim2"],
      "internal_consistency": "HIGH/MEDIUM/LOW",
      "evidence_strength": "STRONG/MEDIUM/WEAK"
    }
  ]
}
"""
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Generate narrative summaries for each cluster"""
        self.log_action("Starting narration", f"{len(state.get('clusters', []))} clusters")
        
        clusters = state.get('clusters', [])
        sources = state.get('scrubbed_sources', [])
        
        if not clusters:
            self.log_action("Narration skipped", "No clusters")
            return state
        
        # Prepare cluster data for prompt
        clusters_text = "\n\n---\n\n".join([
            f"Cluster: {c.label}\nSources: {c.source_ids}\nSummary: {c.narrative_summary}"
            for c in clusters
        ])
        
        # Include source content for each cluster
        source_map = {s['id']: s for s in sources}
        
        prompt = f"""
Create detailed narrative summaries for each cluster.

CLUSTERS:
{clusters_text}

SOURCE CONTENT (for reference):
{json.dumps([{ 'id': s['id'], 'content': s.get('content', '')[:500] } for s in sources], indent=2)}

Return JSON with cluster summaries as specified in system prompt.
"""
        
        try:
            response = await self.generate(prompt, temperature=0.3)
            
            # Parse and update clusters
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "").strip()
            
            result = json.loads(response)
            
            # Update cluster objects with detailed summaries
            summary_map = {s['cluster_id']: s for s in result.get('cluster_summaries', [])}
            
            for cluster in clusters:
                if cluster.cluster_id in summary_map:
                    summary = summary_map[cluster.cluster_id]
                    cluster.narrative_summary = summary.get('detailed_summary', cluster.narrative_summary)
                    cluster.key_claims = summary.get('key_claims', cluster.key_claims)
            
            state['ai_metadata']['narrator_model'] = self.llm.model
            state['ai_metadata']['narrator_cost'] = self.llm.get_total_cost()
            
            self.log_action("Narration complete", f"{len(clusters)} summaries generated")
            
        except Exception as e:
            state['errors'].append(f"Narrator Error: {str(e)}")
            self.log_action("Narration failed", str(e))
        
        return state

narrator_agent = NarratorAgent()
```

---

## 📄 9. `app/agents/arbitrator.py`

```python
"""
Arbitrator Agent.
Identifies contradictions and recommends verification status.
"""
from typing import Dict, Any, List
import json
from app.agents.base import BaseAgent
from app.models import Contradiction, ArbitrationResult

class ArbitratorAgent(BaseAgent):
    """
    Compares clusters to find contradictions and recommend verification status.
    """
    
    @property
    def system_prompt(self) -> str:
        return """
You are an arbitration and fact-checking agent. Compare narrative clusters to identify 
contradictions and recommend a verification status.

VERIFICATION STATUS DEFINITIONS:
- CONFIRMED: All credible sources agree, multiple independent confirmations
- PROBABLE: Most sources agree, minor contradictions, strong evidence
- ALLEGED: Claims made but insufficient verification
- CONTESTED: Significant contradictions between credible sources
- DEBUNKED: Claims proven false by evidence

RULES:
1. Identify SPECIFIC contradictions (not just "they disagree").
2. Rate severity based on importance of the contradiction.
3. Suggest concrete verification questions.
4. Be conservative - if uncertain, recommend lower confidence status.
5. Return ONLY valid JSON.

OUTPUT FORMAT:
{
  "contradictions": [
    {
      "topic": "What is contradicted",
      "cluster_a_id": "id",
      "cluster_a_claim": "What A says",
      "cluster_b_id": "id",
      "cluster_b_claim": "What B says",
      "severity": "LOW/MEDIUM/HIGH/CRITICAL"
    }
  ],
  "verification_questions": ["Question 1", "Question 2"],
  "overall_confidence": 0.0-1.0,
  "recommended_status": "CONFIRMED/PROBABLE/ALLEGED/CONTESTED/DEBUNKED",
  "notes": "Summary of reasoning"
}
"""
    
    async def process(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze contradictions and recommend status"""
        self.log_action("Starting arbitration", f"{len(state.get('clusters', []))} clusters")
        
        clusters = state.get('clusters', [])
        
        if not clusters:
            state['errors'].append("No clusters to arbitrate")
            return state
        
        # Prepare cluster data for prompt
        clusters_text = "\n\n---\n\n".join([
            f"Cluster ID: {c.cluster_id}\nLabel: {c.label}\nSummary: {c.narrative_summary}\nKey Claims: {c.key_claims}"
            for c in clusters
        ])
        
        prompt = f"""
Analyze these narrative clusters for contradictions and recommend verification status.

CLUSTERS:
{clusters_text}

Return JSON with arbitration results as specified in system prompt.
"""
        
        try:
            response = await self.generate(prompt, temperature=0.2)
            
            if response.startswith("```json"):
                response = response.replace("```json", "").replace("```", "").strip()
            
            result = json.loads(response)
            
            # Create ArbitrationResult object
            contradictions = [
                Contradiction(**c) for c in result.get('contradictions', [])
            ]
            
            arbitration = ArbitrationResult(
                contradictions=contradictions,
                verification_questions=result.get('verification_questions', []),
                overall_confidence=min(1.0, max(0.0, result.get('overall_confidence', 0.5))),
                recommended_status=result.get('recommended_status', 'ALLEGED'),
                notes=result.get('notes', '')
            )
            
            state['arbitration'] = arbitration
            state['ai_metadata']['arbitrator_model'] = self.llm.model
            state['ai_metadata']['arbitrator_cost'] = self.llm.get_total_cost()
            state['status'] = 'REVIEW_READY'
            
            self.log_action("Arbitration complete", f"Status: {arbitration.recommended_status}")
            
        except Exception as e:
            state['errors'].append(f"Arbitrator Error: {str(e)}")
            state['status'] = 'ERROR'
            self.log_action("Arbitration failed", str(e))
        
        return state

arbitrator_agent = ArbitratorAgent()
```

---

## 📄 10. `app/graph/workflow.py` ⭐ (LANGGRAPH ORCHESTRATION)

```python
"""
LangGraph workflow orchestration for the multi-agent system.
"""
from typing import Dict, Any, TypedDict, Annotated, Sequence
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from app.agents.clusterer import clusterer_agent
from app.agents.narrator import narrator_agent
from app.agents.arbitrator import arbitrator_agent
from app.privacy import pii_scrubber
from app.models import AIProcessingState
import logging

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    """LangGraph state schema"""
    event_id: str
    raw_sources: list
    scrubbed_sources: list
    clusters: list
    arbitration: dict
    ai_metadata: dict
    cost_usd: float
    errors: list
    status: str

def create_workflow():
    """Create the LangGraph workflow"""
    
    # Initialize state graph
    workflow = StateGraph(AgentState)
    
    # Define nodes
    async def scrub_pii(state: AgentState) -> AgentState:
        """Scrub PII before sending to cloud LLMs"""
        logger.info("[Workflow] Scrubbing PII...")
        scrubbed = pii_scrubber.scrub_sources(state['raw_sources'])
        state['scrubbed_sources'] = scrubbed
        state['ai_metadata']['pii_scrubbed'] = True
        return state
    
    async def run_clusterer(state: AgentState) -> AgentState:
        """Run clustering agent"""
        logger.info("[Workflow] Running Clusterer...")
        state_dict = {k: v for k, v in state.items()}
        result = await clusterer_agent.process(state_dict)
        return {
            **state,
            'clusters': result.get('clusters', []),
            'errors': state.get('errors', []) + result.get('errors', []),
            'ai_metadata': {**state.get('ai_metadata', {}), **result.get('ai_metadata', {})},
            'status': result.get('status', state.get('status'))
        }
    
    async def run_narrator(state: AgentState) -> AgentState:
        """Run narrator agent"""
        logger.info("[Workflow] Running Narrator...")
        state_dict = {k: v for k, v in state.items()}
        result = await narrator_agent.process(state_dict)
        return {
            **state,
            'clusters': result.get('clusters', []),
            'errors': state.get('errors', []) + result.get('errors', []),
            'ai_metadata': {**state.get('ai_metadata', {}), **result.get('ai_metadata', {})},
            'status': result.get('status', state.get('status'))
        }
    
    async def run_arbitrator(state: AgentState) -> AgentState:
        """Run arbitrator agent"""
        logger.info("[Workflow] Running Arbitrator...")
        state_dict = {k: v for k, v in state.items()}
        result = await arbitrator_agent.process(state_dict)
        arbitration_dict = result.get('arbitration')
        if arbitration_dict:
            arbitration_dict = arbitration_dict.__dict__ if hasattr(arbitration_dict, '__dict__') else arbitration_dict
        return {
            **state,
            'arbitration': arbitration_dict,
            'errors': state.get('errors', []) + result.get('errors', []),
            'ai_metadata': {**state.get('ai_metadata', {}), **result.get('ai_metadata', {})},
            'status': result.get('status', state.get('status'))
        }
    
    def should_continue(state: AgentState) -> str:
        """Conditional edge: continue if no errors"""
        if state.get('errors'):
            return "error"
        return "continue"
    
    # Add nodes
    workflow.add_node("scrub_pii", scrub_pii)
    workflow.add_node("clusterer", run_clusterer)
    workflow.add_node("narrator", run_narrator)
    workflow.add_node("arbitrator", run_arbitrator)
    
    # Add edges
    workflow.set_entry_point("scrub_pii")
    workflow.add_edge("scrub_pii", "clusterer")
    workflow.add_edge("clusterer", "narrator")
    workflow.add_edge("narrator", "arbitrator")
    workflow.add_edge("arbitrator", END)
    
    # Compile
    app = workflow.compile()
    return app

# Global workflow instance
workflow = create_workflow()
```

---

## 📄 11. `app/main.py` (FastAPI Entry Point)

```python
"""
FastAPI entry point for AI Service.
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
from app.graph.workflow import workflow
from app.models import SourceDocument, AIProcessingState
from app.utils.llm import llm_client
import logging
import uuid
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Triangulate AI Service", version="1.0.0")

class ProcessRequest(BaseModel):
    event_id: str
    sources: List[Dict[str, Any]]

class ProcessResponse(BaseModel):
    event_id: str
    status: str
    clusters: List[Dict]
    arbitration: Dict
    cost_usd: float
    errors: List[str]

@app.post("/api/v1/process")
async def process_event(request: ProcessRequest):
    """
    Process an event through the multi-agent AI workflow.
    """
    logger.info(f"Processing event: {request.event_id}")
    
    try:
        # Initialize state
        initial_state = {
            "event_id": request.event_id,
            "raw_sources": request.sources,
            "scrubbed_sources": [],
            "clusters": [],
            "arbitration": None,
            "ai_metadata": {},
            "cost_usd": 0.0,
            "errors": [],
            "status": "PROCESSING"
        }
        
        # Run workflow
        result = await workflow.ainvoke(initial_state)
        
        # Calculate total cost
        total_cost = llm_client.get_total_cost()
        
        return ProcessResponse(
            event_id=request.event_id,
            status=result.get('status', 'ERROR'),
            clusters=[c.__dict__ if hasattr(c, '__dict__') else c for c in result.get('clusters', [])],
            arbitration=result.get('arbitration', {}),
            cost_usd=total_cost,
            errors=result.get('errors', [])
        )
        
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/v1/costs")
async def get_costs():
    """Get current session costs"""
    return {"total_cost_usd": llm_client.get_total_cost()}
```

---

## 📄 12. `Dockerfile`

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for Presidio/spaCy
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_lg

# Copy application
COPY . .

# Expose port
EXPOSE 3002

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3002"]
```

---

## 📄 13. `.env.example`

```bash
# LLM API Keys
GEMINI_API_KEY=your_gemini_key_here
QWEN_API_KEY=your_qwen_key_here
CLAUDE_API_KEY=your_claude_key_here
OPENAI_API_KEY=your_openai_key_here

# LLM Configuration
LLM_PROVIDER=gemini
LLM_MODEL_CLUSTER=gemini/gemini-1.5-pro
LLM_MODEL_NARRATE=gemini/gemini-1.5-pro
LLM_MODEL_ARBITRATE=gemini/gemini-1.5-pro
LLM_MODEL_CHEAP=qwen/qwen-72b-chat

# Privacy
ENABLE_PII_SCRUB=true

# Cost Tracking
TRACK_COSTS=true
MONTHLY_BUDGET_USD=100.0
```

---

## 🧪 Usage Example

```python
# From your Node.js backend or directly:
import requests

response = requests.post("http://localhost:3002/api/v1/process", json={
    "event_id": "evt_001",
    "sources": [
        {
            "id": "src_001",
            "url": "https://reuters.com/...",
            "content": "Government reports 5 casualties in strike...",
            "source_type": "news_article",
            "published_at": "2023-10-07T08:00:00Z",
            "author": "Reuters Staff"
        },
        {
            "id": "src_002",
            "url": "https://twitter.com/...",
            "content": "Eyewitness reports 20+ casualties...",
            "source_type": "social_media",
            "published_at": "2023-10-07T07:30:00Z",
            "author": "@eyewitness"
        }
    ]
})

print(response.json())
# Returns clusters, contradictions, and recommended verification status
```

---

## ✅ Next Steps

1.  **Test Locally:** Run `docker compose up` and test the `/api/v1/process` endpoint.
2.  **Tune Prompts:** Adjust clustering prompts based on real-world results.
3.  **Add Caching:** Cache LLM responses for identical source sets.
4.  **Build Admin UI:** Create the human review dashboard in React.

This code provides a **production-ready foundation** for your Dynamic Clustering Agent system.