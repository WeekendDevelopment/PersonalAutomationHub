"""Glue: read unsent items -> format -> send to Telegram -> mark as sent.

Used by both the worker (scheduled digests, alerts) and the bot (/<mode>).
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import asyncpg

from . import db, llm
from .config import Mode, Settings
from .db import Subscriber
from .digest import format_alert, format_digest
from .models import Item
from .telegram import Telegram

ALERT_MAX_AGE = timedelta(hours=6)
ALERTS_PER_RUN = 3


async def send_digest(
    pool: asyncpg.Pool,
    telegram: Telegram,
    settings: Settings,
    tz: ZoneInfo,
    mode: Mode,
    subscriber: Subscriber,
) -> int:
    """Send the mode's top unsent items to one subscriber. Returns how many."""
    items = await db.unsent_items(
        pool, mode.name, subscriber.id, mode.digest_size, mode.max_age_hours
    )
    if not items:
        return 0
    briefing = await llm.briefing(settings, mode.title, items)
    for message in format_digest(mode, items, datetime.now(tz), briefing):
        await telegram.send(subscriber.chat_id, message)
    # Marked only after every message went out: a failed send is retried next time.
    await db.mark_sent(pool, subscriber.id, items, "digest")
    return len(items)


def pick_alerts(mode: Mode, new_items: list[Item], now: datetime) -> list[Item]:
    """Which freshly collected items deserve an immediate push."""
    if mode.alert_score is None:
        return []
    hot = [
        item
        for item in new_items
        if item.score >= mode.alert_score
        and item.published_at is not None
        and now - item.published_at <= ALERT_MAX_AGE
    ]
    return sorted(hot, key=lambda item: item.score, reverse=True)[:ALERTS_PER_RUN]


async def send_alerts(
    pool: asyncpg.Pool, telegram: Telegram, mode: Mode, new_items: list[Item]
) -> int:
    now = datetime.now(timezone.utc)
    alerts = pick_alerts(mode, new_items, now)
    if not alerts:
        return 0
    for subscriber in await db.subscribers_for(pool, mode.name):
        for item in alerts:
            await telegram.send(subscriber.chat_id, format_alert(mode, item, now))
        # Alerted items count as sent, so the next digest does not repeat them.
        await db.mark_sent(pool, subscriber.id, alerts, "alert")
    return len(alerts)
