"""RSS / Atom feeds, parsed with feedparser."""

from datetime import datetime, timezone

import feedparser
import httpx

from ..config import Source
from ..models import Item, clean_text

MAX_ENTRIES = 50
MAX_SUMMARY_CHARS = 500


def parse(content: bytes | str, source_name: str) -> list[Item]:
    """Turn feed XML into items. No network - this is what the tests exercise."""
    items = []
    for entry in feedparser.parse(content).entries[:MAX_ENTRIES]:
        title = clean_text(entry.get("title", ""))
        url = (entry.get("link") or "").strip()
        if not title or not url:
            continue
        # feedparser normalises dates to a UTC time tuple.
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        items.append(
            Item(
                title=title,
                url=url,
                source=source_name,
                summary=clean_text(entry.get("summary", ""))[:MAX_SUMMARY_CHARS],
                published_at=datetime(*parsed[:6], tzinfo=timezone.utc) if parsed else None,
            )
        )
    return items


async def fetch(client: httpx.AsyncClient, source: Source) -> list[Item]:
    if not source.url:
        raise ValueError(f"rss source {source.name!r} needs a url")
    response = await client.get(source.url)
    response.raise_for_status()
    return parse(response.content, source.name)
