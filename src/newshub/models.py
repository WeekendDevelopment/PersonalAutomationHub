"""The one data shape every part of newshub passes around."""

import html
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Item:
    title: str
    url: str
    source: str
    summary: str = ""
    published_at: datetime | None = None  # always timezone-aware (UTC)
    popularity: int = 0  # e.g. Hacker News points; 0 when the source has none
    score: float = 0.0
    id: int | None = None  # database id, set only for stored items


def clean_text(raw: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()
