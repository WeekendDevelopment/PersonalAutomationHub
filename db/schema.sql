-- newshub schema. Postgres runs this once, on first start with an empty data
-- volume (it is mounted into /docker-entrypoint-initdb.d).
-- Every statement is idempotent so it can also be re-applied by hand:
--   docker compose exec -T postgres psql -U newshub -d newshub < db/schema.sql

-- One row per collected article, per mode. The same URL may appear in two
-- modes (with different scores), but never twice in one mode.
CREATE TABLE IF NOT EXISTS items (
    id           BIGSERIAL PRIMARY KEY,
    mode         TEXT             NOT NULL,
    source       TEXT             NOT NULL,
    url          TEXT             NOT NULL,
    title        TEXT             NOT NULL,
    summary      TEXT             NOT NULL DEFAULT '',
    score        DOUBLE PRECISION NOT NULL DEFAULT 0,
    popularity   INTEGER          NOT NULL DEFAULT 0,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ      NOT NULL DEFAULT now(),
    UNIQUE (mode, url)
);

CREATE INDEX IF NOT EXISTS items_mode_score_idx ON items (mode, score DESC);

-- People (Telegram chats) who receive news. v1 only ever creates one row:
-- the owner. The table exists so more subscribers can be added later without
-- a redesign. modes = NULL means "all modes".
CREATE TABLE IF NOT EXISTS subscribers (
    id         BIGSERIAL PRIMARY KEY,
    chat_id    BIGINT      NOT NULL UNIQUE,
    name       TEXT        NOT NULL DEFAULT '',
    is_owner   BOOLEAN     NOT NULL DEFAULT false,
    modes      TEXT[],
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- At most one owner, enforced by the database: the first /start wins.
CREATE UNIQUE INDEX IF NOT EXISTS subscribers_one_owner_idx
    ON subscribers (is_owner) WHERE is_owner;

-- What has been sent to whom. An item is "unsent" for a subscriber when
-- there is no row here, so each subscriber has their own read position.
CREATE TABLE IF NOT EXISTS deliveries (
    subscriber_id BIGINT      NOT NULL REFERENCES subscribers (id) ON DELETE CASCADE,
    item_id       BIGINT      NOT NULL REFERENCES items (id) ON DELETE CASCADE,
    kind          TEXT        NOT NULL DEFAULT 'digest',  -- 'digest' or 'alert'
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (subscriber_id, item_id)
);
