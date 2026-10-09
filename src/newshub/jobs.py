"""The queue contract between services.

The api and the bot never import the worker; they only put a job *name* on
the Redis queue. That keeps the services loosely coupled: a worker written in
another language only has to understand these names.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

COLLECT_ALL = "enqueue_collection"  # no arguments: fan out one job per source
COLLECT_SOURCE = "collect_source"  # (mode_name, source_name)
SEND_DIGEST = "send_digest"  # (mode_name,)


def redis_settings(redis_url: str) -> RedisSettings:
    return RedisSettings.from_dsn(redis_url)


async def connect(redis_url: str) -> ArqRedis:
    return await create_pool(redis_settings(redis_url))
