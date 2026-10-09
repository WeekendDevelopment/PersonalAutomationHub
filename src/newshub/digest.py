"""Turns items into Telegram HTML messages. Pure functions, no I/O."""

from datetime import datetime
from html import escape

from .config import Mode
from .models import Item

TELEGRAM_LIMIT = 4096  # max characters in one Telegram message
MAX_TITLE_CHARS = 200


def age(published_at: datetime | None, now: datetime) -> str:
    if published_at is None:
        return ""
    seconds = max((now - published_at).total_seconds(), 0)
    if seconds < 3600:
        return f"{max(int(seconds // 60), 1)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _item_line(item: Item, now: datetime) -> str:
    title = item.title
    if len(title) > MAX_TITLE_CHARS:
        title = title[: MAX_TITLE_CHARS - 1] + "…"
    meta = " · ".join(part for part in (item.source, age(item.published_at, now)) if part)
    return f'<a href="{escape(item.url, quote=True)}">{escape(title)}</a>\n<i>{escape(meta)}</i>'


def split_blocks(blocks: list[str], limit: int = TELEGRAM_LIMIT) -> list[str]:
    """Join blocks with blank lines into as few messages as fit the limit.

    A block is never cut in half, so HTML tags always stay balanced.
    """
    messages: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) <= limit or not current:
            current = candidate
        else:
            messages.append(current)
            current = block
    if current:
        messages.append(current)
    return messages


def format_digest(
    mode: Mode, items: list[Item], now: datetime, briefing: str | None = None
) -> list[str]:
    """Build the digest as one or more Telegram HTML messages."""
    blocks = [f"{mode.emoji} <b>{escape(mode.title)} digest</b> · {now:%a %d %b, %H:%M}"]
    if briefing:
        blocks.append(f"<i>{escape(briefing.strip())}</i>")
    for number, item in enumerate(items, start=1):
        blocks.append(f"<b>{number}.</b> {_item_line(item, now)}")
    return split_blocks(blocks)


def format_alert(mode: Mode, item: Item, now: datetime) -> str:
    return f"🚨 {mode.emoji} <b>{escape(mode.title)} alert</b>\n{_item_line(item, now)}"
