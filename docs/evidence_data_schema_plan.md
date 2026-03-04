## 📸 Multimedia Evidence Schema Extension

### Core Principle: **Evidence ≠ Event**
Each piece of media (screenshot, X post, video) is a **separate evidence object** linked to an event. This allows you to:
- Track when evidence was **captured** vs. when the event **occurred**
- Verify each piece independently
- Show conflicting evidence side-by-side

---

### Extended Schema Structure

```json
{
  "event_id": "evt_2023_10_07_001",
  "timestamp_utc": "2023-10-07T06:30:00Z",
  "event_type": "PHYSICAL_EVENT",
  "verification_status": "PROBABLE",
  "confidence_score": 75,
  
  "--- EVIDENCE ATTACHMENTS ---": "Array of all multimedia evidence",
  "evidence": [
    {
      "evidence_id": "evd_001",
      "evidence_type": "SOCIAL_MEDIA_POST",
      "platform": "X_TWITTER",
      
      "--- ORIGINAL CONTENT ---": "What the post said",
      "original_url": "https://x.com/user/status/1234567890",
      "archived_url": "https://archive.org/wayback/...",
      "warc_file": "s3://bucket/evidence/evt_001_001.warc.gz",
      
      "post_author": "@eyewitness_gaza",
      "post_timestamp": "2023-10-07T06:45:00Z",
      "post_content": "Huge explosion heard in southern Tel Aviv #rocket",
      "media_attachments": [
        {
          "type": "IMAGE",
          "original_url": "https://pbs.twimg.com/media/...",
          "archived_url": "https://archive.today/...",
          "thumbnail_url": "https://cdn.yoursite.com/thumb/evd_001_img1.jpg",
          "hash_sha256": "a3f5b8c9d2e1f4..."
        }
      ],
      
      "--- VERIFICATION METADATA ---": "Bellingcat-style verification",
      "verification_status": "PARTIALLY_VERIFIED",
      "verification_checks": [
        {
          "check_type": "GEOLOCATION",
          "result": "CONFIRMED",
          "method": "Google Earth Pro + landmark matching",
          "notes": "Building in background matches coordinates 31.0461, 34.8516",
          "verified_by": "analyst_003",
          "verified_at": "2023-10-07T14:00:00Z"
        },
        {
          "check_type": "TIMESTAMP",
          "result": "CONFIRMED",
          "method": "Shadow analysis + sun position calculator",
          "notes": "Shadow angle consistent with 06:45 local time",
          "verified_by": "analyst_003",
          "verified_at": "2023-10-07T14:30:00Z"
        },
        {
          "check_type": "REVERSE_IMAGE_SEARCH",
          "result": "NO_PRIOR_APPEARANCE",
          "method": "Google Images, Yandex, TinEye",
          "notes": "Image not found before this post date",
          "verified_by": "automated_tool",
          "verified_at": "2023-10-07T13:00:00Z"
        },
        {
          "check_type": "ACCOUNT_AUTHENTICITY",
          "result": "SUSPICIOUS",
          "method": "Account age, posting history analysis",
          "notes": "Account created 3 days before event, low follower count",
          "verified_by": "analyst_005",
          "verified_at": "2023-10-07T15:00:00Z"
        }
      ],
      
      "--- ARCHIVAL INTEGRITY ---": "Tamper-evident storage [[11]]",
      "capture_method": "ARCHIVEBOX_WARC",
      "capture_timestamp": "2023-10-07T07:00:00Z",
      "capture_tool": "ArchiveBox v0.6.2",
      "integrity_hash": "sha256:b4c7d9e2f1a8...",
      "chain_of_custody": [
        {
          "action": "CAPTURED",
          "timestamp": "2023-10-07T07:00:00Z",
          "actor": "system_bot"
        },
        {
          "action": "VERIFIED",
          "timestamp": "2023-10-07T14:00:00Z",
          "actor": "analyst_003"
        },
        {
          "action": "LINKED_TO_EVENT",
          "timestamp": "2023-10-07T16:00:00Z",
          "actor": "analyst_003"
        }
      ],
      
      "--- VISUALIZATION HINTS ---": "How to display in UI",
      "display_priority": "HIGH",
      "thumbnail_available": true,
      "content_warning": "EXPLOSIVE_CONTENT",
      "requires_blur": true
    },
    
    {
      "evidence_id": "evd_002",
      "evidence_type": "NEWS_SCREENSHOT",
      "platform": "WEBSITE",
      "original_url": "https://reuters.com/article/...",
      "archived_url": "https://web.archive.org/...",
      "warc_file": "s3://bucket/evidence/evt_001_002.warc.gz",
      "screenshot_url": "https://cdn.yoursite.com/screenshots/evd_002.png",
      "headline": "Missile Attack Confirmed by Defense Ministry",
      "publication_date": "2023-10-07T08:00:00Z",
      
      "verification_status": "VERIFIED",
      "verification_checks": [
        {
          "check_type": "SOURCE_CREDIBILITY",
          "result": "HIGH",
          "method": "Known reputable news organization",
          "notes": "Reuters has on-ground correspondents",
          "verified_by": "analyst_001",
          "verified_at": "2023-10-07T09:00:00Z"
        }
      ],
      
      "capture_method": "FULL_PAGE_SCREENSHOT",
      "capture_timestamp": "2023-10-07T08:15:00Z",
      "capture_tool": "Playwright + ArchiveBox",
      "integrity_hash": "sha256:c5d8e3f2b9a1...",
      
      "display_priority": "MEDIUM",
      "thumbnail_available": true,
      "content_warning": null,
      "requires_blur": false
    },
    
    {
      "evidence_id": "evd_003",
      "evidence_type": "USER_SUBMISSION",
      "platform": "DIRECT_UPLOAD",
      
      "--- USER CONTEXT ---": "Who submitted this",
      "submitted_by": "user_12345",
      "submission_timestamp": "2023-10-08T10:00:00Z",
      "user_claim": "I was there, this is what I saw",
      "user_credibility_score": 45,
      "user_verification_status": "UNVERIFIED_CONTRIBUTOR",
      
      "media_attachments": [
        {
          "type": "VIDEO",
          "original_filename": "IMG_20231007_063000.mp4",
          "archived_url": "s3://bucket/evidence/evt_001_003.mp4",
          "thumbnail_url": "https://cdn.yoursite.com/thumb/evd_003_vid1.jpg",
          "hash_sha256": "d6e9f4a3c2b1...",
          "metadata_extracted": {
            "exif_data": {
              "device": "iPhone 14 Pro",
              "capture_time": "2023-10-07T06:32:00Z",
              "location_gps": "REMOVED_BY_USER"
            },
            "manipulation_detection": {
              "error_level_analysis": "NO_TAMPERING_DETECTED",
              "deepfake_score": 0.02
            }
          }
        }
      ],
      
      "verification_status": "UNVERIFIED",
      "verification_checks": [
        {
          "check_type": "METADATA_ANALYSIS",
          "result": "INCONCLUSIVE",
          "method": "Exif data extraction",
          "notes": "GPS data stripped, timestamp present but unverified",
          "verified_by": "automated_tool",
          "verified_at": "2023-10-08T10:05:00Z"
        },
        {
          "check_type": "CONTENT_MATCHING",
          "result": "PARTIAL_MATCH",
          "method": "Frame comparison with evd_001",
          "notes": "Same location, different angle, consistent timeline",
          "verified_by": "analyst_007",
          "verified_at": "2023-10-08T12:00:00Z"
        }
      ],
      
      "capture_method": "DIRECT_UPLOAD",
      "capture_timestamp": "2023-10-08T10:00:00Z",
      "integrity_hash": "sha256:e7f1a5b4c3d2...",
      
      "display_priority": "LOW",
      "thumbnail_available": true,
      "content_warning": "POTENTIALLY_GRAPHIC",
      "requires_blur": true
    }
  ],
  
  "--- EVIDENCE SUMMARY ---": "Aggregated for quick UI display",
  "evidence_summary": {
    "total_pieces": 3,
    "verified_count": 1,
    "partially_verified_count": 1,
    "unverified_count": 1,
    "platforms_represented": ["X_TWITTER", "WEBSITE", "DIRECT_UPLOAD"],
    "strongest_evidence_id": "evd_002",
    "conflicting_evidence_ids": ["evd_001", "evd_003"]
  }
}
```

---

## 🎨 Visualization Implementation

### 1. **Evidence Indicator Icons on Timeline Nodes**

```
┌─────────────────────────────────────────┐
│  💥 Missile Launch Detected             │
│  [📸 3] [🎥 1] [📰 2]                   │
│  Oct 7, 06:30 UTC                       │
└─────────────────────────────────────────┘
     │    │    │
     │    │    └── News Articles (2)
     │    └─────── Videos (1)
     └──────────── Photos/Screenshots (3)
```

**Visual Logic:**
- 📸 = Image evidence count
- 🎥 = Video evidence count
- 📰 = News/Article evidence count
- **Color-coded border:** Green = all verified, Orange = mixed, Red = all unverified

### 2. **Evidence Panel (Click to Expand)**

When user clicks a timeline node, show a **Evidence Drawer** with:

```
┌─────────────────────────────────────────────────────┐
│ EVIDENCE FOR: Missile Launch Detected               │
├─────────────────────────────────────────────────────┤
│ FILTER: [All] [Verified Only] [Unverified Only]    │
├─────────────────────────────────────────────────────┤
│                                                     │
│ ✅ VERIFIED (1)                                     │
│ ┌─────────────────────────────────────────────┐    │
│ │ [THUMBNAIL] Reuters Article                 │    │
│ │ Published: Oct 7, 08:00                     │    │
│ │ ✓ Source Credibility: HIGH                  │    │
│ │ [View Archived Copy] [View Verification]    │    │
│ └─────────────────────────────────────────────┘    │
│                                                     │
│ ⚠️ PARTIALLY VERIFIED (1)                           │
│ ┌─────────────────────────────────────────────┐    │
│ │ [THUMBNAIL] X Post @eyewitness_gaza         │    │
│ │ Posted: Oct 7, 06:45                        │    │
│ │ ✓ Geolocation: CONFIRMED                    │    │
│ │ ✓ Timestamp: CONFIRMED                      │    │
│ │ ⚠ Account Authenticity: SUSPICIOUS          │    │
│ │ [View Archived Copy] [View Verification]    │    │
│ └─────────────────────────────────────────────┘    │
│                                                     │
│ ❌ UNVERIFIED (1)                                   │
│ ┌─────────────────────────────────────────────┐    │
│ │ [THUMBNAIL] User Submission (Blurred)       │    │
│ │ Submitted: Oct 8, 10:00                     │    │
│ │ ⚠ Metadata: INCONCLUSIVE                    │    │
│ │ ⚠ User Credibility: LOW                     │    │
│ │ [View Archived Copy] [Request Verification] │    │
│ └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

### 3. **Verification Badge System**

Each evidence item gets a **verification badge** based on checks:

| Badge | Meaning | Display |
|-------|---------|---------|
| ✅ **VERIFIED** | 3+ checks passed, no failures | Green checkmark |
| ⚠️ **PARTIAL** | Some checks passed, some inconclusive | Yellow warning |
| ❌ **UNVERIFIED** | No checks completed or all failed | Red X |
| 🚩 **CONTESTED** | Conflicting evidence exists | Orange flag |
| 🗑️ **DEBUNKED** | Proven false/manipulated | Grey trash |

---

## 🔧 Technical Implementation

### 1. **Archival Pipeline** (Critical for Evidence Preservation)

Based on OSINT best practices [[10]], [[11]]:

```
User Submits URL/Screenshot
        ↓
[ArchiveBox] Captures WARC + Screenshot + Metadata
        ↓
[Hash Generator] Creates SHA256 for integrity
        ↓
[S3/GCS Storage] Stores with chain of custody log
        ↓
[Verification Queue] Sends to analysts for checks
        ↓
[Database] Links evidence to event
```

**Tools to use:**
- **ArchiveBox** – Self-hosted web archiving (WARC format) [[10]]
- **Playwright** – Automated screenshot capture
- **InVID Plugin** – Video/image verification [[5]]
- **ExifTool** – Metadata extraction
- **FotoForensics** – Error Level Analysis for manipulation detection

### 2. **Database Schema (PostgreSQL Example)**

```sql
-- Evidence table
CREATE TABLE evidence (
    evidence_id UUID PRIMARY KEY,
    event_id UUID REFERENCES events(event_id),
    evidence_type VARCHAR(50),
    platform VARCHAR(50),
    original_url TEXT,
    archived_url TEXT,
    warc_file_path TEXT,
    integrity_hash VARCHAR(64),
    verification_status VARCHAR(50),
    confidence_score INTEGER,
    display_priority VARCHAR(20),
    content_warning VARCHAR(100),
    requires_blur BOOLEAN,
    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

-- Verification checks table
CREATE TABLE verification_checks (
    check_id UUID PRIMARY KEY,
    evidence_id UUID REFERENCES evidence(evidence_id),
    check_type VARCHAR(50),
    result VARCHAR(50),
    method TEXT,
    notes TEXT,
    verified_by VARCHAR(100),
    verified_at TIMESTAMPTZ
);

-- Media attachments table
CREATE TABLE media_attachments (
    attachment_id UUID PRIMARY KEY,
    evidence_id UUID REFERENCES evidence(evidence_id),
    media_type VARCHAR(20),
    original_url TEXT,
    archived_url TEXT,
    thumbnail_url TEXT,
    hash_sha256 VARCHAR(64),
    metadata_json JSONB
);

-- Chain of custody table
CREATE TABLE chain_of_custody (
    custody_id UUID PRIMARY KEY,
    evidence_id UUID REFERENCES evidence(evidence_id),
    action VARCHAR(50),
    actor VARCHAR(100),
    timestamp TIMESTAMPTZ
);
```

### 3. **Frontend Component Structure (React)**

```jsx
<TimelineNode event={event}>
  <EvidenceIndicators count={event.evidence_summary.total_pieces} />
  
  <EvidencePanel event={event}>
    <EvidenceFilter filters={['all', 'verified', 'unverified']} />
    
    {event.evidence.map(evidence => (
      <EvidenceCard 
        evidence={evidence}
        verificationBadge={getVerificationBadge(evidence)}
        thumbnail={evidence.thumbnail_url}
        requiresBlur={evidence.requires_blur}
      >
        <VerificationChecks checks={evidence.verification_checks} />
        <ArchivedLink url={evidence.archived_url} />
        <ChainOfCustody log={evidence.chain_of_custody} />
      </EvidenceCard>
    ))}
  </EvidencePanel>
</TimelineNode>
```

---

## ⚠️ Critical Considerations

### 1. **Legal & Ethical**
- **Consent:** User-submitted content needs explicit consent for display
- **Privacy:** Blur faces, license plates, identifiable locations for civilians
- **Defamation:** Clearly label unverified claims as "ALLEGED"
- **Archival Rights:** Some platforms prohibit archiving (check ToS)

### 2. **Storage Costs**
- WARC files + screenshots + videos = **expensive**
- **Solution:** Store thumbnails on CDN, full files in cold storage (S3 Glacier)
- **Retention Policy:** Auto-delete unverified evidence after 90 days unless promoted

### 3. **Verification Workload**
- Manual verification doesn't scale
- **Solution:** 
  - Automated checks first (reverse image search, metadata extraction)
  - Human analysts only for high-significance events (score > 7)
  - Community verification (trusted contributor program)

### 4. **Evidence Decay**
- Social media posts get deleted
- **Solution:** Archive **immediately** upon discovery (not when adding to timeline)
- Use **multiple archival services** (Archive.org + ArchiveBox + Perma.cc)

---

## 📋 Quick Reference: Evidence Type Handling

| Evidence Type | Capture Method | Verification Priority | Display Treatment |
|--------------|----------------|----------------------|-------------------|
| **X/Twitter Post** | ArchiveBox WARC + Screenshot | HIGH (deleted frequently) | Show archived link prominently |
| **News Article** | Full-page screenshot + PDF | MEDIUM | Show publisher logo, date |
| **User Video** | Download + hash + metadata extract | HIGH (manipulation risk) | Blur by default, click to unblur |
| **User Photo** | Download + hash + ELA analysis | HIGH | Blur by default, click to unblur |
| **Government Report** | PDF archive + checksum | LOW (stable) | Show official seal if available |
| **Sensor Data** | API capture + timestamp log | LOW (technical) | Show raw data chart |

---

## References
 **Bellingcat's verification methodology** [[1]], [[9]] and **OSINT archival best practices** [[10]], [[11]], 