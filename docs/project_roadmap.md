# Project Roadmap

## Overview

This roadmap outlines the planned enhancements and integrations for Triangulate, prioritized by impact and alignment with the project's goals of multi-agent investigative journalism and AI-assisted fact verification.

---

## Priority 1: Web UI Enhancements

The existing React web UI provides case management and review capabilities. The following enhancements improve the human review workflow.

### 1.1 Annotation & Commenting System
- Add comments on evidence items, claims, and narratives
- Thread-based discussions for review collaboration
- Mentions and notifications

**Files to modify**: `frontend/src/pages/tabs/EvidenceTab.tsx`, `frontend/src/pages/tabs/ClaimsTab.tsx`

### 1.2 Evidence Flagging
- Mark specific evidence for follow-up investigation
- Create flag categories (needs-verification, conflicting, key-piece)
- Filter case views by flagged items

**Files to modify**: `frontend/src/types/backend-models.ts`, EvidenceTab components

### 1.3 Audit Trail
- Track all human review decisions with timestamps
- Record who resolved each exception and why
- Export audit log for compliance reporting

**Files to modify**: `backend/http/` endpoints, database models for audit events

### 1.4 Side-by-Side Source Comparison
- Split-view to compare two sources or versions
- Highlight differences in claims and verifications
- Link sources that corroborate or contradict each other

**Files to modify**: `frontend/src/pages/CorroborationNetwork.tsx`, new comparison component

---

## Priority 2: OSINT Integration

Passive ingestion of data from external OSINT tools via CLI streaming.

### 2.1 OSINT Ingestion CLI Command
```bash
triangulate osint ingest --tool <tool-name> --file <data>
```

**New file**: `src/cli/commands/osint.py`

### 2.2 Supported Tool Imports

| Tool | Format | Implementation |
|------|--------|----------------|
| **SpiderFoot** | XML/JSON | Parse and import entities, relationships, and findings into case |
| **Hunchly** | JSON export | Import archived pages with timestamps and metadata |
| **TinEye** | CSV/JSON | Import image verification results, original source URLs |
| **Babel X** | JSON | Import monitored narratives and cross-language coverage data |
| **Sherlock** | JSON | Import social media account presence for entities |

### 2.3 Streaming Mode
```bash
triangulate osint stream --tool spiderfoot --watch <directory>
```
- Watch directory for new output files
- Automatically ingest and link to active case
- Stream results to web UI in real-time via WebSocket

**Files to modify**: `src/cli/commands/osint.py`, `src/ingester/`, WebSocket handlers

### 2.4 Case Linking
- All ingested OSINT data linked to specific case
- New `OsintArtifact` model with source tool, raw data, and case relationship
- Query OSINT artifacts alongside native evidence

**Files to modify**: `src/storage/models.py`, `src/cases/`

---

## Priority 3: Future Considerations

Lower priority items for future development.

### 3.1 Multimodal Verification
- Image verification with TinEye API integration
- Video keyframe extraction and verification
- Audio transcription verification

**Status**: Deferred, depends on external API integrations

### 3.2 Real-Time Monitoring Alerts
- Email/webhook notifications for case updates
- New information detection for monitored topics
- Anomaly alerts when verification status changes

**Status**: Future enhancement

### 3.3 Knowledge Base Poisoning Detection
- Detect when external data sources may be compromised
- Monitor for systematic bias injection in evidence
- Alert when fact-checking pipeline may be under attack

**Research reference**: Fact2Fiction (AAAI-2026) - adversarial attacks on fact-checking

### 3.4 Multi-Language Expansion
- Expand beyond English sources
- Add cross-language claim verification
- Integrate translation services for source materials

### 3.5 Collaborative Review Features
- Multi-user review workflows
- Role-based access control (analyst, reviewer, admin)
- Review assignment and delegation

---

## Implementation Notes

### Phase 1: Web UI Enhancements
Focus on improving the existing review workflow without changing backend architecture significantly.

### Phase 2: OSINT CLI Integration
Build the ingestion pipeline in the CLI. This keeps OSINT integration lightweight and scriptable while the web UI gains read access to imported data.

### Phase 3: Streaming & Real-Time
Once basic ingestion works, add directory watching and WebSocket streaming for live updates.

---

## Changelog

- 2026-03-19: Initial roadmap created
