"""
JARVIS-MKIII — news.py
Fetches headlines from RSS feeds. No API key required.
Categories: Tech/AI, World, Egypt, Financial
"""

from __future__ import annotations
import httpx
import xml.etree.ElementTree as ET
from datetime import datetime

FEEDS = {
    "tech":     "https://feeds.feedburner.com/TheHackersNews",
    "ai":       "https://techcrunch.com/feed/",
    "world":    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "egypt":    "https://www.egyptindependent.com/feed/",
    "finance":  "https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC,^DJI&region=US&lang=en-US",
}


async def fetch_feed(url: str, max_items: int = 3) -> list[str]:
    """Fetch RSS feed and return list of headline strings."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, follow_redirects=True,
                                    headers={"User-Agent": "JARVIS-MKIII/3.2"})
            resp.raise_for_status()

        root = ET.fromstring(resp.text)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}

        headlines = []
        # RSS format
        for item in root.findall(".//item")[:max_items]:
            title = item.findtext("title", "").strip()
            if title:
                headlines.append(title)

        # Atom format fallback
        if not headlines:
            for entry in root.findall(".//atom:entry", ns)[:max_items]:
                title = entry.findtext("atom:title", "", ns).strip()
                if title:
                    headlines.append(title)

        return headlines
    except Exception as e:
        print(f"[NEWS] Failed to fetch {url}: {e}")
        return []


async def get_morning_briefing() -> str:
    """
    Fetch headlines across all categories and return a
    JARVIS-style briefing string for TTS.
    """
    import asyncio

    results = await asyncio.gather(
        fetch_feed(FEEDS["tech"],    max_items=1),
        fetch_feed(FEEDS["ai"],      max_items=1),
        fetch_feed(FEEDS["world"],   max_items=1),
        fetch_feed(FEEDS["egypt"],   max_items=1),
        fetch_feed(FEEDS["finance"], max_items=1),
    )

    tech_headlines    = results[0]
    ai_headlines      = results[1]
    world_headlines   = results[2]
    egypt_headlines   = results[3]
    finance_headlines = results[4]

    # Boot briefing: maximum 3 items across all categories
    all_items: list[tuple[str, str]] = []  # (category, headline)
    for h in (tech_headlines + ai_headlines)[:1]:
        all_items.append(("technology", h))
    for h in world_headlines[:1]:
        all_items.append(("world", h))
    for h in egypt_headlines[:1]:
        all_items.append(("Egypt", h))
    for h in finance_headlines[:1]:
        all_items.append(("markets", h))
    all_items = all_items[:3]  # hard cap at 3

    sections = []
    cat_groups: dict[str, list[str]] = {}
    for cat, headline in all_items:
        cat_groups.setdefault(cat, []).append(headline)

    if "technology" in cat_groups:
        sections.append("In technology: " + ". ".join(cat_groups["technology"]) + ".")
    if "world" in cat_groups:
        sections.append("World news: " + ". ".join(cat_groups["world"]) + ".")
    if "Egypt" in cat_groups:
        sections.append("From Egypt: " + ". ".join(cat_groups["Egypt"]) + ".")
    if "markets" in cat_groups:
        sections.append("Markets: " + ". ".join(cat_groups["markets"]) + ".")

    if not sections:
        return "News feeds are currently unavailable, sir."

    return " ".join(sections)
