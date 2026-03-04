"""Test fixtures for Triangulate tests."""

# Sample RSS feed data
SAMPLE_RSS_ENTRY = {
    "title": "Test Article: Breaking News Event",
    "link": "https://example.com/article1",
    "description": "This is a test article about an important event that happened.",
    "published_parsed": (2024, 3, 1, 12, 0, 0, 0, 0, 0),
    "author": "Test Author",
}

# Sample article data
SAMPLE_ARTICLE = {
    "title": "Test Article: Breaking News Event",
    "content": "This is a test article about an important event that happened. Multiple sources report that something occurred.",
    "timestamp": "2024-03-01T12:00:00",
    "link": "https://example.com/article1",
    "author": "Test Author",
    "source_name": "Test Source",
    "source_url": "https://example.com",
}

# Sample claims extracted from article
SAMPLE_CLAIMS = [
    {
        "claim": "Something important happened on March 1st",
        "who": ["Entity1", "Entity2"],
        "when": "March 1st, 2024",
        "where": "Test Location",
        "confidence": "HIGH",
    },
    {
        "claim": "Multiple sources report the event",
        "who": ["Sources"],
        "when": "March 1st, 2024",
        "where": "Unknown",
        "confidence": "MEDIUM",
    },
]

# Sample event data
SAMPLE_EVENT = {
    "id": "test-event-1",
    "timestamp": "2024-03-01T12:00:00",
    "title": "Test Event: Breaking News",
    "summary": "This is a test event summary",
    "verification_status": "PROBABLE",
    "claims": SAMPLE_CLAIMS,
    "narratives": [
        {
            "cluster_id": "0",
            "stance_summary": "Test narrative about the event",
            "key_themes": ["theme1", "theme2"],
            "main_entities": ["Entity1", "Entity2"],
            "claim_count": 2,
        }
    ],
    "source_url": "https://example.com/article1",
    "source_name": "Test Source",
}
