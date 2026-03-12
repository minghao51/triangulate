
## ⚠️ 6. Critical Points of Interest & Suggestions

### **1. Cost Management (Hosted APIs)**
*   **Risk:** Running agents on every headline can get expensive ($0.50 - $5.00 per event depending on complexity).
*   **Suggestion:** 
    *   **Tiered Analysis:** Run cheap clustering on *all* headlines. Only run deep arbitration on **High Significance** events (score > 5).
    *   **Budget Alarm:** Add a hard cap in your code (e.g., "Stop AI tasks if monthly cost > $50").
    *   **Model Routing:** Use **LiteLLM** to route simple tasks to cheaper models (e.g., Qwen-72B) and complex reasoning to premium models (e.g., Gemini 1.5 Pro).

### **2. Privacy & Data Sovereignty**
*   **Risk:** Sending data to Google/Alibaba means they process your text.
*   **Suggestion:** 
    *   **Scrubbing:** Run **Presidio** locally before sending text to API. Remove names, phone numbers, exact addresses. Send only "Explosion reported in [City]" not "Explosion killed John Doe at [Street]".
    *   **Enterprise API:** If possible, use Google/Anthropic **Enterprise** tiers which promise not to train on your data.
    *   **Local Archive:** Keep the **original** unscrubbed text locally in your DB. Only send the scrubbed version to the cloud.

### **3. Dynamic Clustering Prompt Engineering**
*   **Risk:** AI might cluster based on language (English vs Arabic) instead of perspective.
*   **Suggestion:** Explicitly prompt for **Stance**, not **Language**.
    *   *Prompt:* "Group these sources by their **claim regarding the event**, not by language or region. Identify conflicting narratives."
*   **Validation:** In the Admin UI, show the user which sources ended up in which cluster. Allow the human to **drag/drop** sources between clusters if the AI messed up.

### **4. Hallucination Mitigation (Source Grounding)**
*   **Risk:** AI summarizes a claim that wasn't actually in the text.
*   **Suggestion:** **Citation Enforcement.**
    *   Prompt the AI: "Every summary sentence must include a citation ID linking back to the source text."
    *   UI Feature: Hover over an AI summary sentence → Highlight the original source text snippet that supports it. If no highlight appears, it's a hallucination.

### **5. Abstraction for Future Cloud Migration**
*   **Suggestion:** Use the **Repository Pattern** for Storage and LLM.
    *   `interface LLMProvider { generate(prompt): string }`
    *   `class GeminiProvider implements LLMProvider {...}`
    *   `class QwenProvider implements LLMProvider {...}`
    *   *Benefit:* If Gemini raises prices or blocks you, you switch one config line to Qwen without rewriting code.
