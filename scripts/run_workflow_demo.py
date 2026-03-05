#!/usr/bin/env python3
"""Demo script to run AI workflow on a news article URL.

This script fetches an article from a URL, processes it through the AI workflow,
and displays the extracted claims, narratives, and parties.

Usage:
    uv run scripts/run_workflow_demo.py <article_url>
"""

import asyncio
import sys
import json
import toml
from datetime import datetime
from urllib.parse import urlparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ai.workflow import AIWorkflow


async def fetch_article_content(url: str) -> dict:
    """Fetch article content from URL.

    Args:
        url: Article URL

    Returns:
        Article dictionary with title, content, etc.
    """
    import httpx
    from trafilatura import fetch_url, extract

    print(f"Fetching article from: {url}")

    try:
        # Try trafilatura first (better for complex sites)
        downloaded = fetch_url(url)
        if downloaded:
            result = extract(downloaded, include_comments=False, include_tables=False)
            if result and len(result) > 200:
                # Get title from metadata
                title = ""
                try:
                    import trafilatura.metadata

                    metadata = trafilatura.metadata.Metadata(downloaded)
                    title = metadata.title or ""
                except Exception:
                    pass

                # Extract source name from URL
                parsed_url = urlparse(url)
                source_name = parsed_url.netloc.replace("www.", "")

                article = {
                    "title": title or "Untitled Article",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                    "link": url,
                    "author": "",
                    "source_name": source_name,
                    "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
                }

                print(f"✓ Fetched article (trafilatura): {title[:60]}...")
                print(f"✓ Content length: {len(result)} characters\n")

                return article

        # Fallback to BeautifulSoup
        print("Trafilatura extraction failed, using fallback...")
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Try to extract title
        title = ""
        for tag in ["h1", "title"]:
            element = soup.find(tag)
            if element:
                title = element.get_text().strip()
                break
                title = element.get_text().strip()
                break

        # Try to extract content from common article containers
        content_selectors = [
            "article",
            '[class*="article"]',
            '[class*="story"]',
            '[class*="content"]',
            "main",
        ]

        content = ""
        for selector in content_selectors:
            element = soup.select_one(selector)
            if element:
                # Remove script and style elements
                for script in element(["script", "style", "nav", "footer", "header"]):
                    script.decompose()
                content = element.get_text(separator="\n", strip=True)
                if len(content) > 200:
                    break

        # Fallback: get all paragraphs
        if not content or len(content) < 200:
            paragraphs = soup.find_all("p")
            content = "\n".join([p.get_text().strip() for p in paragraphs])

        # Extract source name from URL
        parsed_url = urlparse(url)
        source_name = parsed_url.netloc.replace("www.", "")

        article = {
            "title": title or "Untitled Article",
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "link": url,
            "author": "",
            "source_name": source_name,
            "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
        }

        print(f"✓ Fetched article: {title[:60]}...")
        print(f"✓ Content length: {len(content)} characters\n")

        return article

    except Exception as e:
        print(f"✗ Error fetching article: {e}")
        sys.exit(1)


def pretty_print_results(event_data: dict):
    """Pretty print the workflow results.

    Args:
        event_data: Processed event data from AIWorkflow
    """
    print("\n" + "=" * 80)
    print("AI WORKFLOW RESULTS")
    print("=" * 80 + "\n")

    # Event Overview
    print("📰 EVENT OVERVIEW")
    print("-" * 80)
    print(f"Title:       {event_data.get('title', 'N/A')}")
    print(f"Status:      {event_data.get('verification_status', 'N/A')}")
    print(f"Source:      {event_data.get('source_name', 'N/A')}")
    print(f"URL:         {event_data.get('source_url', 'N/A')}")
    print()

    # Claims
    claims = event_data.get("claims", [])
    print(f"📝 EXTRACTED CLAIMS ({len(claims)} total)")
    print("-" * 80)
    if claims:
        for i, claim in enumerate(claims, 1):
            print(f"\n[{i}] {claim.get('claim', 'N/A')}")
            print(f"    Who:        {', '.join(claim.get('who', [])) or 'N/A'}")
            print(f"    When:       {claim.get('when', 'N/A')}")
            print(f"    Where:      {claim.get('where', 'N/A')}")
            print(f"    Confidence: {claim.get('confidence', 'N/A')}")
            print(f"    Status:     {claim.get('verification_status', 'N/A')}")
    else:
        print("No claims extracted.")
    print()

    # Narratives
    narratives = event_data.get("narratives", [])
    print(f"🎭 NARRATIVES ({len(narratives)} total)")
    print("-" * 80)
    if narratives:
        for i, narrative in enumerate(narratives, 1):
            print(f"\n[Narrative {i}] Cluster ID: {narrative.get('cluster_id', 'N/A')}")
            print(f"    Claims: {narrative.get('claim_count', 0)}")
            print(f"    Stance: {narrative.get('stance_summary', 'N/A')}")
            print(f"    Themes: {', '.join(narrative.get('key_themes', [])) or 'N/A'}")
            print(
                f"    Entities (Parties): {', '.join(narrative.get('main_entities', [])) or 'N/A'}"
            )
    else:
        print("No narratives generated.")
    print()

    # Parties
    parties = event_data.get("parties", [])
    print(f"🎭 IDENTIFIED PARTIES ({len(parties)} total)")
    print("-" * 80)
    if parties:
        for i, party in enumerate(parties, 1):
            print(f"\n[Party {i}] {party.get('canonical_name', 'N/A')}")
            print(f"    Aliases: {', '.join(party.get('aliases', []))}")
            if party.get('reasoning'):
                print(f"    Reasoning: {party.get('reasoning')}")
    else:
        print("No parties identified.")
    print()

    # Summary
    print("📊 SUMMARY")
    print("-" * 80)
    print(f"Total Claims:      {len(claims)}")
    print(f"Total Narratives:  {len(narratives)}")
    print(f"Verification:      {event_data.get('verification_status', 'N/A')}")

    # Parties/Entities Summary
    all_entities = set()
    for narrative in narratives:
        all_entities.update(narrative.get("main_entities", []))
    for claim in claims:
        all_entities.update(claim.get("who", []))

    print(f"Identified Parties: {', '.join(sorted(all_entities)) or 'N/A'}")
    print()

    # Full JSON Output (optional)
    print("\n" + "=" * 80)
    print("FULL JSON OUTPUT")
    print("=" * 80 + "\n")
    print(json.dumps(event_data, indent=2, default=str))


async def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: uv run scripts/run_workflow_demo.py <article_url>")
        print("\nExample:")
        print(
            "  uv run scripts/run_workflow_demo.py https://www.bbc.com/news/world-12345678"
        )
        sys.exit(1)

    url = sys.argv[1]

    # Load config
    config_path = Path("config.toml")
    with open(config_path) as f:
        config = toml.load(f)

    # Fetch article
    article = await fetch_article_content(url)

    # Initialize workflow
    workflow = AIWorkflow(config)

    # Process article
    print("Processing article through AI workflow...")
    print("This may take a minute...\n")

    event_data = await workflow.process_article(article)

    if not event_data:
        print("✗ Failed to process article. No claims were extracted.")
        sys.exit(1)

    # Display results
    pretty_print_results(event_data)


if __name__ == "__main__":
    asyncio.run(main())
