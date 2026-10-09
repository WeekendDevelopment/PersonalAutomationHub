"""Hacker News front page, via the free Algolia search API (no key needed).

Options: min_points - only stories with at least this many points.
"""

from datetime import datetime, timezone

import httpx

from ..config import Source
from ..models import Item

API_URL = "https://hn.algolia.com/api/v1/search"


def parse(data: dict, source_name: str) -> list[Item]:
    items = []
    for hit in data.get("hits", []):
        title = (hit.get("title") or "").strip()
        if not title:
            continue
        created = hit.get("created_at_i")
        items.append(
            Item(
                title=title,
                # "Ask HN" style posts have no external URL; link the discussion.
                url=hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                source=source_name,
                published_at=datetime.fromtimestamp(created, timezone.utc) if created else None,
                popularity=hit.get("points") or 0,
            )
        )
    return items


async def fetch(client: httpx.AsyncClient, source: Source) -> list[Item]:
    params = {"tags": "front_page", "hitsPerPage": 50}
    min_points = source.options.get("min_points")
    if min_points:
        params["numericFilters"] = f"points>={int(min_points)}"
    response = await client.get(source.url or API_URL, params=params)
    response.raise_for_status()
    return parse(response.json(), source.name)
