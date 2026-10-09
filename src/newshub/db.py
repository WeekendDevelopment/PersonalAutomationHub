"""All SQL lives here. Tables are defined in db/schema.sql."""

from dataclasses import dataclass

import asyncpg

from .models import Item


@dataclass
class Subscriber:
    id: int
    chat_id: int
    is_owner: bool


async def connect(database_url: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(database_url, min_size=1, max_size=5)


def _to_item(row: asyncpg.Record) -> Item:
    return Item(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        source=row["source"],
        summary=row["summary"],
        published_at=row["published_at"],
        popularity=row["popularity"],
        score=row["score"],
    )


# --- items ------------------------------------------------------------------


async def insert_items(pool: asyncpg.Pool, mode: str, items: list[Item]) -> list[Item]:
    """Store items, skipping any (mode, url) already present. Returns the new ones."""
    new = []
    async with pool.acquire() as conn:
        for item in items:
            item_id = await conn.fetchval(
                """
                INSERT INTO items (mode, source, url, title, summary, score, popularity, published_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (mode, url) DO NOTHING
                RETURNING id
                """,
                mode, item.source, item.url, item.title, item.summary,
                item.score, item.popularity, item.published_at,
            )
            if item_id is not None:  # None means it was a duplicate
                item.id = item_id
                new.append(item)
    return new


async def unsent_items(
    pool: asyncpg.Pool, mode: str, subscriber_id: int, limit: int, max_age_hours: int
) -> list[Item]:
    """The best recent items this subscriber has not been sent yet."""
    rows = await pool.fetch(
        """
        SELECT i.* FROM items i
        WHERE i.mode = $1
          AND COALESCE(i.published_at, i.fetched_at) > now() - make_interval(hours => $4)
          AND NOT EXISTS (
              SELECT 1 FROM deliveries d
              WHERE d.item_id = i.id AND d.subscriber_id = $2
          )
        ORDER BY i.score DESC, COALESCE(i.published_at, i.fetched_at) DESC
        LIMIT $3
        """,
        mode, subscriber_id, limit, max_age_hours,
    )
    return [_to_item(row) for row in rows]


async def recent_items(pool: asyncpg.Pool, mode: str, limit: int) -> list[Item]:
    rows = await pool.fetch(
        "SELECT * FROM items WHERE mode = $1 ORDER BY fetched_at DESC, score DESC LIMIT $2",
        mode, limit,
    )
    return [_to_item(row) for row in rows]


async def mark_sent(pool: asyncpg.Pool, subscriber_id: int, items: list[Item], kind: str) -> None:
    await pool.execute(
        """
        INSERT INTO deliveries (subscriber_id, item_id, kind)
        SELECT $1::bigint, unnest($2::bigint[]), $3::text
        ON CONFLICT DO NOTHING
        """,
        subscriber_id, [item.id for item in items], kind,
    )


# --- subscribers --------------------------------------------------------------


async def claim_owner(pool: asyncpg.Pool, chat_id: int, name: str) -> bool:
    """Make this chat the owner if there is none yet. True if it just became owner.

    The unique index on is_owner makes this safe even if two chats race.
    """
    new_id = await pool.fetchval(
        """
        INSERT INTO subscribers (chat_id, name, is_owner) VALUES ($1, $2, true)
        ON CONFLICT DO NOTHING
        RETURNING id
        """,
        chat_id, name,
    )
    return new_id is not None


async def get_subscriber(pool: asyncpg.Pool, chat_id: int) -> Subscriber | None:
    row = await pool.fetchrow(
        "SELECT id, chat_id, is_owner FROM subscribers WHERE chat_id = $1", chat_id
    )
    return Subscriber(**row) if row else None


async def subscribers_for(pool: asyncpg.Pool, mode: str) -> list[Subscriber]:
    rows = await pool.fetch(
        "SELECT id, chat_id, is_owner FROM subscribers WHERE modes IS NULL OR $1 = ANY(modes)",
        mode,
    )
    return [Subscriber(**row) for row in rows]
