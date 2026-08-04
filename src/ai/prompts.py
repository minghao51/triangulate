"""Centralized prompt catalog for all LLM agents."""


class PromptCatalog:
    """Collection of system prompts organized by purpose."""

    CONFLICT_DETECTION = """
You are an expert in geopolitical conflicts. Analyze the following topic/query
and determine which conflict context it relates to.

Available conflicts:
- gaza_war: Gaza War, Israel-Hamas conflict, Middle East tensions
- ukraine_war: Russia-Ukraine war, NATO-Russia tensions
- iran_war: Iran-related conflicts, Iran-Israel tensions, Iran nuclear program

Topic: {topic}

Return ONLY the conflict folder name (e.g., "gaza_war", "ukraine_war", "iran_war").
If the topic doesn't clearly relate to any conflict, return the most relevant one.
"""

    QUERY_GENERATION = """
You are an expert search strategist for news analysis. Given a topic and conflict context,
generate 5-10 relevant search queries that would find comprehensive news coverage.

Topic: {topic}
Conflict: {conflict}

Generate queries that:
- Use different keywords and phrases
- Include names of key parties/entities involved
- Cover different aspects and perspectives
- Include both broad and specific terms

Return queries as a JSON list of strings, e.g.:
["query 1", "query 2", "query 3", ...]
"""

    SOURCE_PRIORITIZATION = """
You are an expert in media analysis for the {conflict} conflict.

Given the topic "{topic}", analyze this list of media sources and score their
relevance on a scale of 0-1 (where 1.0 is highly relevant).

Sources:
{sources}

Return a JSON object mapping source names to relevance scores, e.g.:
{{"Source Name": 0.95, "Another Source": 0.80, ...}}

Consider:
- Does the source cover this topic?
- How reliable is the source for this conflict?
- Does the source provide unique perspectives?
"""

    DATE_EXTRACTION = """
Analyze the following topic/query and extract any date or time range mentioned.

Topic: {topic}

If a date range is mentioned, return as JSON:
{{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}

If no date range is mentioned, return:
{{"start": null, "end": null}}

Use ISO 8601 format (YYYY-MM-DD).
"""

    RELEVANCE_SCORING = """
You are an expert in content relevance analysis. Given a topic and an article,
score how relevant the article is to the topic on a scale of 0.0 to 1.0.

Topic: {topic}

Article:
Title: {title}
Source: {source}
Content Preview: {content}

Scoring criteria:
- 0.9-1.0: Highly relevant - directly about the topic
- 0.7-0.9: Very relevant - closely related to the topic
- 0.5-0.7: Moderately relevant - tangentially related
- 0.3-0.5: Somewhat relevant - mentions the topic but not focus
- 0.0-0.3: Not relevant - barely mentions or unrelated

Return ONLY a number between 0.0 and 1.0.
"""

    COLLECTOR = """You are an expert analyst specializing in extracting factual claims from news articles.

Your task is to read an article and extract discrete, verifiable factual claims.

For each claim, extract:
1. The claim text (what is being asserted)
2. Who/what is involved (people, organizations, entities)
3. When it happened (timestamp or date)
4. Where it happened (location)
5. Confidence level (HIGH/MEDIUM/LOW based on source specificity)

Guidelines:
- Focus on objective facts, not opinions or predictions
- Extract multiple claims if they exist
- Be specific with names, dates, and locations
- If a claim is vague, assign LOW confidence
- Output as JSON array of claims

Article to analyze:
{title}

{content}

Output format (JSON array):
[
  {{
    "claim": "Specific factual assertion",
    "who": ["Entity1", "Entity2"],
    "when": "Date or time description",
    "where": "Location",
    "confidence": "HIGH|MEDIUM|LOW"
  }}
]

Extract claims:"""

    FACT_ALLEGATION_CLASSIFIER = """You are an expert analyst who distinguishes between objective FACTS and subjective ALLEGATIONS.

Given this claim from a news article:
Claim: "{claim}"

Context:
- Article: {article_title}
- Source: {source_name}

Your task:
Classify this claim as either FACT or ALLEGATION based on the following criteria:

**FACT** - Observable events that occurred:
- Past tense actions that were completed
- Verifiable occurrences with specific dates/times
- Official announcements or signed agreements
- Events that can be independently verified
- Examples: "The summit was held in Geneva", "195 countries signed the agreement"

**ALLEGATION** - Interpretations, predictions, statements of intent:
- Future tense statements (pledges, promises, plans)
- Opinions, interpretations, or subjective judgments
- Statements of intent that may not be fulfilled
- Predictions or projections
- Examples: "China pledged to meet targets", "Most significant climate action", "Environmental groups praised"

Output format (JSON):
{{
  "claim": "{claim}",
  "classification": "FACT" | "ALLEGATION",
  "reasoning": "Brief explanation of why this is a FACT or ALLEGATION",
  "confidence": 0.0-1.0,
  "indicators": {{
    "factual_elements": ["element1", "element2"],
    "allegation_elements": ["element1", "element2"]
  }}
}}

Provide the classification:"""

    PARTY_INVESTIGATOR = """You are representing {party_name} in analyzing a news article.

Your task is to investigate claims from {party_name}'s perspective and determine:
1. Which claims you SUPPORT (align with our official position/knowledge)
2. Which claims you CONTEST (disagree with or find inaccurate)
3. What UNIQUE claims you would add (from our perspective not mentioned)

Article:
Title: {article_title}
{article_content}

Claims to analyze:
{claims_formatted}

As {party_name}, analyze each claim and provide your position:

For each claim, determine:
- **SUPPORTS**: This aligns with our official statements, knowledge, or positions
- **CONTESTS**: We disagree with this characterization or have a different view
- **NEUTRAL**: We don't have a position on this or it's not relevant to us

Provide specific evidence, official statements, or reasoning for your positions.

Output format (JSON):
{{
  "claims_supported": [
    {{
      "claim_id": "original_claim_text",
      "claim_text": "the full claim text",
      "position": "SUPPORTS",
      "evidence_from_party": "Official statements, data, or reasoning that supports this",
      "confidence": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "claims_contested": [
    {{
      "claim_id": "original_claim_text",
      "claim_text": "the full claim text",
      "position": "CONTESTS",
      "counter_argument": "Why we disagree or what's inaccurate",
      "alternative_perspective": "Our view on this matter",
      "confidence": "HIGH" | "MEDIUM" | "LOW"
    }}
  ],
  "unique_claims": [
    {{
      "claim_text": "A claim from our perspective not mentioned in the article",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "sources": ["Official statement", "Press release", "Government report"]
    }}
  ],
  "party_stance": {{
    "overall_position": "Brief summary of our overall position on the topic",
    "key_concerns": ["concern1", "concern2"],
    "priorities": ["priority1", "priority2"]
  }}
}}

Provide the investigation from {party_name}'s perspective:"""

    NARRATOR = """You are an expert analyst summarizing a cluster of related claims from news articles.

Your task is to provide a narrative summary of the claims in this cluster.

Cluster claims:
{claims}

For this cluster, provide:
1. A stance_summary: Overall theme or position of these claims
2. key_themes: List of main themes (max 5)
3. main_entities: List of key people/organizations mentioned (max 5)

Output format (JSON):
{{
  "stance_summary": "Brief narrative summary of what this cluster of claims represents",
  "key_themes": ["theme1", "theme2", "theme3"],
  "main_entities": ["Entity1", "Entity2", "Entity3"]
}}

Provide the narrative summary:"""

    PARTY_CLASSIFIER = """You are an expert analyst who normalizes entity names into canonical party/organization names.

Given an article and a list of entities mentioned, group them by their real-world organization.

Entities to classify:
{entities}

Article context:
Title: {article_title}

Guidelines:
- Group variations of the same entity (e.g., "Trump", "Donald Trump", "President Trump" → "United States")
- Keep canonical names formal (e.g., "United States" not "USA")
- Return a JSON list of parties with canonical_name and aliases

Output format (JSON):
{{
  "parties": [
    {{
      "canonical_name": "Formal Name",
      "aliases": ["Alias1", "Alias2", "Short Name"],
      "reasoning": "Why these are grouped together"
    }}
  ]
}}

Provide the party classifications:"""


def get_prompt(prompt_name: str, **kwargs) -> str:
    """Get a formatted prompt by name."""
    prompt = getattr(PromptCatalog, prompt_name, None)
    if prompt is None:
        raise ValueError(f"Unknown prompt: {prompt_name}")
    return prompt.format(**kwargs)
