"""Helpers for fetching a single article URL into the intake pipeline."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse


async def fetch_article_content(url: str) -> dict:
    """Fetch article content from a URL using trafilatura with BeautifulSoup fallback."""
    import httpx
    from bs4 import BeautifulSoup

    try:
        from trafilatura import extract, fetch_url

        downloaded = fetch_url(url)
        if downloaded:
            result = extract(downloaded, include_comments=False, include_tables=False)
            if result and len(result) > 200:
                title = ""
                try:
                    import trafilatura.metadata

                    metadata = trafilatura.metadata.Metadata(downloaded)
                    title = metadata.title or ""
                except Exception:
                    pass

                parsed_url = urlparse(url)
                return {
                    "title": title or "Untitled Article",
                    "content": result,
                    "timestamp": datetime.now().isoformat(),
                    "link": url,
                    "url": url,
                    "author": "",
                    "source_name": parsed_url.netloc.replace("www.", ""),
                    "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
                    "source_type": "manual",
                }
    except ImportError:
        pass

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.get(url)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    title = ""
    for tag in ["h1", "title"]:
        element = soup.find(tag)
        if element:
            title = element.get_text().strip()
            break

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
            for script in element(["script", "style", "nav", "footer", "header"]):
                script.decompose()
            content = element.get_text(separator="\n", strip=True)
            if len(content) > 200:
                break

    if not content or len(content) < 200:
        paragraphs = soup.find_all("p")
        content = "\n".join([p.get_text().strip() for p in paragraphs])

    parsed_url = urlparse(url)
    source_name = parsed_url.netloc.replace("www.", "")
    return {
        "title": title or "Untitled Article",
        "content": content,
        "timestamp": datetime.now().isoformat(),
        "link": url,
        "url": url,
        "author": "",
        "source_name": source_name,
        "source_url": f"{parsed_url.scheme}://{parsed_url.netloc}",
        "source_type": "manual",
    }
