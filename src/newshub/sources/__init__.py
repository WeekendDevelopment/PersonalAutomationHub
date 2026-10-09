"""Source adapters (plug-ins).

Each module in this package is one source type and exposes a single function:

    async def fetch(client: httpx.AsyncClient, source: Source) -> list[Item]

A source in modes.yaml with `type: rss` is handled by sources/rss.py, and so
on. To add a source type, add one file here - nothing else needs to change.
"""

import importlib

import httpx

from ..config import Source
from ..models import Item

USER_AGENT = "newshub/0.1 (personal news reader)"


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}
    )


async def fetch(client: httpx.AsyncClient, source: Source) -> list[Item]:
    try:
        adapter = importlib.import_module(f"{__name__}.{source.type}")
    except ModuleNotFoundError:
        raise ValueError(f"unknown source type {source.type!r} (source {source.name!r})")
    return await adapter.fetch(client, source)
