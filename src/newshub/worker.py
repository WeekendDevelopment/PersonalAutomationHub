"""Background worker (arq): the job queue consumer and the cron scheduler.

Run with:  arq newshub.worker.WorkerSettings
"""

import logging
from datetime import datetime

from arq import Retry, cron

from . import db, delivery, jobs, pipeline, sources
from .config import Settings, load_config
from .telegram import Telegram

log = logging.getLogger("newshub.worker")

settings = Settings.from_env()
config = load_config()


async def startup(ctx: dict) -> None:
    ctx["pool"] = await db.connect(settings.database_url)
    ctx["http"] = sources.http_client()
    ctx["telegram"] = Telegram(settings.telegram_token) if settings.telegram_token else None
    if ctx["telegram"] is None:
        log.warning("TELEGRAM_BOT_TOKEN is not set: collecting news but sending nothing")


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()
    await ctx["pool"].close()
    if ctx["telegram"]:
        await ctx["telegram"].close()


async def enqueue_collection(ctx: dict) -> int:
    """Cron + on demand: put one collect job per source on the queue."""
    count = 0
    for mode in config.modes.values():
        for source in mode.sources:
            await ctx["redis"].enqueue_job(jobs.COLLECT_SOURCE, mode.name, source.name)
            count += 1
    return count


async def collect_source(ctx: dict, mode_name: str, source_name: str) -> str:
    """Fetch one source, score its items, store the new ones, push alerts."""
    mode = config.modes.get(mode_name)
    source = mode.source(source_name) if mode else None
    if source is None:
        return "skipped: no longer in modes.yaml"

    try:
        items = await pipeline.collect_source(ctx["http"], mode, source)
    except Exception as error:
        # Retry with backoff: 1 min, 2 min, 3 min. After max_tries arq gives up
        # until the next scheduled collection.
        log.warning("fetch failed for %s/%s: %r", mode_name, source_name, error)
        raise Retry(defer=ctx["job_try"] * 60) from error

    new_items = await db.insert_items(ctx["pool"], mode.name, items)
    alerts = 0
    if ctx["telegram"] and new_items:
        alerts = await delivery.send_alerts(ctx["pool"], ctx["telegram"], mode, new_items)
    return f"{len(items)} fetched, {len(new_items)} new, {alerts} alerts"


async def send_digest(ctx: dict, mode_name: str) -> str:
    mode = config.modes.get(mode_name)
    if mode is None or ctx["telegram"] is None:
        return "skipped"
    sent = 0
    for subscriber in await db.subscribers_for(ctx["pool"], mode.name):
        sent += await delivery.send_digest(
            ctx["pool"], ctx["telegram"], settings, config.tz, mode, subscriber
        )
    return f"{sent} items sent"


async def digest_tick(ctx: dict) -> None:
    """Runs every minute: enqueue a digest for each mode whose local time has come."""
    now = datetime.now(config.tz)
    for mode in config.modes.values():
        if now.strftime("%H:%M") in mode.digest_times:
            # The job id makes this idempotent: one digest per mode per minute.
            await ctx["redis"].enqueue_job(
                jobs.SEND_DIGEST, mode.name, _job_id=f"digest:{mode.name}:{now:%Y%m%d%H%M}"
            )


class WorkerSettings:
    redis_settings = jobs.redis_settings(settings.redis_url)
    functions = [enqueue_collection, collect_source, send_digest]
    cron_jobs = [
        cron(
            enqueue_collection,
            minute=set(range(0, 60, config.collect_every_minutes)),
            run_at_startup=True,
        ),
        cron(digest_tick),  # every minute, at second 0
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_tries = 4
    job_timeout = 120
