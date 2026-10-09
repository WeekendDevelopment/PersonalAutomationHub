"""Fetch + score. No database here, so the CLI preview can reuse it as-is."""

from datetime import datetime, timedelta, timezone

import httpx

from . import sources
from .config import Mode, Source
from .models import Item
from .scoring import score_item


async def collect_source(client: httpx.AsyncClient, mode: Mode, source: Source) -> list[Item]:
    """Fetch one source and return its scored, non-blocked, recent items."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=mode.max_age_hours)
    kept = []
    for item in await sources.fetch(client, source):
        if item.published_at and item.published_at < cutoff:
            continue
        score = score_item(item, mode, source)
        if score is None:
            continue
        item.score = score
        kept.append(item)
    return kept


def rank(items: list[Item]) -> list[Item]:
    """Best first: highest score, then newest. One entry per URL."""
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(items, key=lambda i: (i.score, i.published_at or oldest), reverse=True)
    seen: set[str] = set()
    return [i for i in ordered if not (i.url in seen or seen.add(i.url))]
