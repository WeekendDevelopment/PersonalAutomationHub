"""Keyword scoring. Pure functions, no I/O - easy to test and to reason about.

score = sum of matched interest weights (doubled when the hit is in the title)
      + the source's boost
      + a popularity bonus (0 to 3, logarithmic)
"""

import math
import re
from functools import lru_cache

from .config import Mode, Source
from .models import Item

MAX_POPULARITY_BONUS = 3.0


@lru_cache(maxsize=None)
def _pattern(keyword: str) -> re.Pattern[str]:
    # Whole-word match: "go" must not match "google", but "c++" and
    # "event-driven" still work, which plain \b would get wrong.
    return re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)", re.IGNORECASE)


def matches(keyword: str, text: str) -> bool:
    return bool(_pattern(keyword).search(text))


def popularity_bonus(popularity: int) -> float:
    """10 points -> ~1, 100 -> ~2, 1000+ -> 3 (capped)."""
    if popularity <= 0:
        return 0.0
    return min(math.log10(popularity + 1), MAX_POPULARITY_BONUS)


def score_item(item: Item, mode: Mode, source: Source) -> float | None:
    """Score one item for a mode. Returns None when a block keyword matches."""
    if any(matches(k, item.title) or matches(k, item.summary) for k in mode.block):
        return None

    score = 0.0
    for keyword, weight in mode.interests.items():
        if matches(keyword, item.title):
            score += 2 * weight
        elif matches(keyword, item.summary):
            score += weight

    score += source.boost + popularity_bonus(item.popularity)
    return round(score, 2)
