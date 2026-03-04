### 1. Core Philosophy (ICG-Inspired)
Before the code, here are the rules embedded in this schema:
1.  **Separate Observation from Interpretation:** A missile launch (observation) is different from "Country X attacked" (interpretation/claim).
2.  **Tiered Sourcing:** A government press release is weighted differently than a sensor reading or a random tweet.
3.  **Dynamic Truth:** An event's status can change (e.g., from "Rumor" to "Confirmed" to "Debunked"). The schema tracks this history.
4.  **Explicit Uncertainty:** If something cannot be verified, the schema records *why* (e.g., "No access to zone").

---

### 2. The Data Schema (JSON Structure)

```json
{
  "event_id": "evt_2023_10_07_001",
  "timestamp_utc": "2023-10-07T06:30:00Z",
  "location": {
    "lat": 31.0461,
    "lon": 34.8516,
    "region": "Southern Israel",
    "access_status": "CONTESTED_ZONE" 
  },
  
  "--- CLASSIFICATION ---": "Defines what kind of node this is",
  "event_type": "PHYSICAL_EVENT", 
  "sub_type": "EXPLOSION",
  "narrative_claim": "Hamas rocket fire caused explosion", 
  "claim_attribution": "IDF Spokesperson",

  "--- VERIFICATION CORE ---": "The ICG-inspired truth engine",
  "verification_status": "PROBABLE", 
  "confidence_score": 75, 
  "verification_method": "TRIANGULATED_OSINT",
  "verification_limitation": "No independent observers on ground due to security lockdown",

  "--- SOURCES ---": "Triangulation data",
  "sources": [
    {
      "source_id": "src_001",
      "name": "IDF Official Telegram",
      "type": "GOVT_OFFICIAL",
      "tier": 1,
      "url": "https://t.me/...",
      "claim": "Intercepted 500 rockets",
      "reliability_weight": 0.6 
    },
    {
      "source_id": "src_002",
      "name": "Local Resident Video",
      "type": "EYEWITNESS_OSINT",
      "tier": 2,
      "url": "https://twitter.com/...",
      "claim": "Heavy explosions heard",
      "reliability_weight": 0.8
    },
    {
      "source_id": "src_003",
      "name": "Seismic Sensor Data",
      "type": "TECHNICAL_SENSOR",
      "tier": 1,
      "url": "https://usgs.gov/...",
      "claim": "Impact detected at coordinates",
      "reliability_weight": 0.95
    }
  ],

  "--- VISUALIZATION METADATA ---": "Directly feeds your UI logic",
  "significance_score": 9, 
  "visual_group": "CONFLICT_ESCALATION",
  "tags": ["rocket_fire", "civilian_impact", "unverified_claim"],

  "--- EVOLUTION HISTORY ---": "Tracks how truth changes over time",
  "status_history": [
    {
      "updated_at": "2023-10-07T07:00:00Z",
      "status": "UNVERIFIED_RUMOR",
      "note": "Initial social media reports only"
    },
    {
      "updated_at": "2023-10-07T10:00:00Z",
      "status": "PROBABLE",
      "note": "Corroborated by seismic data and multiple eyewitnesses"
    }
  ],

  "--- RELATIONSHIPS ---": "For graph connections",
  "related_events": ["evt_2023_10_07_005", "evt_2023_10_06_099"],
  "causality_type": "RETALIATION" 
}
```

---

### 3. Key Field Explanations & Visualization Mapping

Here is how this schema translates directly into your visual library (e.g., Vis.js or D3):

#### A. `verification_status` & `confidence_score`
*   **Schema Values:** `CONFIRMED`, `PROBABLE`, `ALLEGED`, `CONTESTED`, `DEBUNKED`.
*   **Visualization Logic:**
    *   **CONFIRMED (80-100 score):** Solid Green Node.
    *   **PROBABLE (60-79 score):** Solid Yellow/Orange Node.
    *   **ALLEGED (40-59 score):** Dashed Outline Node (Indicates claim only).
    *   **DEBUNKED (0-30 score):** Greyed out or Strikethrough Node.
*   **Why:** This prevents "false equivalence." A rumor looks visually distinct from a sensor reading.

#### B. `event_type` vs. `narrative_claim`
*   **Schema:** Separates the physical reality (`EXPLOSION`) from the story (`Hamas fired`).
*   **Visualization Logic:**
    *   If `event_type` is `PHYSICAL_EVENT`, show an **Icon** (e.g., 💥).
    *   If `event_type` is `NARRATIVE_ONLY` (e.g., "President says he will win"), show a **Speech Bubble Icon** 🗣️.
*   **Why:** Distinguishes *what happened* from *what people say happened*.

#### C. `sources` (Tiered)
*   **Schema:** Sources have a `tier` and `reliability_weight`.
*   **Visualization Logic:**
    *   **Hover Interaction:** When hovering over a node, display a "Source Confidence Bar."
    *   **Filter:** Add a UI toggle: `Hide Single-Source Events`. If an event only has 1 source in the `sources` array, hide it unless significance is 10.
*   **Why:** Enforces ICG's triangulation principle.

#### D. `status_history`
*   **Schema:** An array of past statuses.
*   **Visualization Logic:**
    *   **Animation:** If a node changes from `ALLEGED` to `CONFIRMED`, the node pulses or changes color dynamically.
    *   **Detail Panel:** Clicking the node shows a timeline of *verification*, not just the event. "At 7:00 AM this was a rumor. At 10:00 AM it was confirmed."
*   **Why:** Shows the *process* of truth, which is critical for historical accuracy.

#### E. `significance_score`
*   **Schema:** Integer 1-10.
*   **Visualization Logic:**
    *   **Node Size:** Radius = `significance_score * 2px`.
    *   **Filter Slider:** User sets slider to "5". All nodes < 5 disappear.
*   **Why:** Prevents timeline clutter. Not every tweet deserves equal space.

---

### 4. Implementation Example: "The Missile Launch"

Here is how two different perspectives on the same event would look in your data, allowing you to visualize the conflict of narratives.

**Event A (The Physical Fact)**
```json
{
  "event_id": "evt_100",
  "timestamp": "2023-10-07T06:30:00Z",
  "event_type": "PHYSICAL_EVENT",
  "sub_type": "PROJECTILE_LAUNCH",
  "verification_status": "CONFIRMED",
  "confidence_score": 95,
  "sources": [ {"type": "TECHNICAL_SENSOR", "tier": 1} ]
}
```
*Visual:* Large, Solid Green Circle. Icon: 🚀.

**Event B (The Attribution Claim)**
```json
{
  "event_id": "evt_101",
  "timestamp": "2023-10-07T06:35:00Z",
  "event_type": "NARRATIVE_CLAIM",
  "narrative_claim": "Group X launched the projectile",
  "verification_status": "CONTESTED",
  "confidence_score": 50,
  "sources": [ 
      {"type": "GOVT_OFFICIAL", "claim": "Group X did it"}, 
      {"type": "GROUP_X_STATEMENT", "claim": "We did not do it"} 
  ]
}
```
*Visual:* Medium, Dashed Orange Circle. Icon: 🗣️. Connected to Event A with a "CLAIMS_RESPONSIBILITY" line.

---

## References
Based on the **International Crisis Group (ICG)** methodology, I have designed a data schema that moves beyond simple "True/False" binaries. ICG's core principles are **triangulation** (cross-referencing sources), **attribution** (who said what), and **transparency about limitations** (admitting when verification isn't possible).

Here is the concrete data schema designed to support your visualization requirements (linear timeline, fact vs. perspective, significance filtering).
