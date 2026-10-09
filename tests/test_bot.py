"""Bot command routing, with the database, queue and Telegram replaced by fakes."""

import asyncio

import pytest

from newshub import bot as bot_module
from newshub.bot import Bot
from newshub.config import Config, Settings
from newshub.db import Subscriber

OWNER_CHAT = 111
STRANGER_CHAT = 999


class FakeTelegram:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, html):
        self.sent.append((chat_id, html))


class FakeRedis:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.jobs.append((name, *args))


@pytest.fixture
def bot(monkeypatch):
    state = {"owner": None, "digests": []}

    async def claim_owner(pool, chat_id, name):
        if state["owner"] is None:
            state["owner"] = chat_id
            return True
        return False

    async def get_subscriber(pool, chat_id):
        if chat_id == state["owner"]:
            return Subscriber(id=1, chat_id=chat_id, is_owner=True)
        return None

    async def send_digest(pool, telegram, settings, tz, mode, subscriber):
        state["digests"].append(mode.name)
        return 0

    monkeypatch.setattr(bot_module.db, "claim_owner", claim_owner)
    monkeypatch.setattr(bot_module.db, "get_subscriber", get_subscriber)
    monkeypatch.setattr(bot_module.delivery, "send_digest", send_digest)

    config = Config.model_validate(
        {"modes": {"f1": {"name": "f1", "sources": [{"name": "s", "url": "https://x"}]}}}
    )
    bot = Bot(
        settings=Settings("", "", "", "", "", ""),
        config=config,
        pool=None,
        redis=FakeRedis(),
        telegram=FakeTelegram(),
    )
    bot.state = state
    return bot


def say(bot, chat_id, text):
    asyncio.run(bot.handle({"chat": {"id": chat_id, "first_name": "Sam"}, "text": text}))


def test_first_start_becomes_owner(bot):
    say(bot, OWNER_CHAT, "/start")
    assert bot.state["owner"] == OWNER_CHAT
    assert "owner" in bot.telegram.sent[0][1]


def test_other_chats_are_ignored(bot):
    say(bot, OWNER_CHAT, "/start")
    bot.telegram.sent.clear()
    for text in ("/start", "/help", "/f1", "/refresh"):
        say(bot, STRANGER_CHAT, text)
    assert bot.telegram.sent == []
    assert bot.redis.jobs == []
    assert bot.state["digests"] == []


def test_commands_before_any_owner_are_ignored(bot):
    say(bot, OWNER_CHAT, "/f1")
    assert bot.telegram.sent == []


def test_mode_command_sends_digest_or_says_nothing_new(bot):
    say(bot, OWNER_CHAT, "/start")
    say(bot, OWNER_CHAT, "/F1@my_newshub_bot please")
    assert bot.state["digests"] == ["f1"]
    assert "Nothing new" in bot.telegram.sent[-1][1]


def test_refresh_enqueues_collection(bot):
    say(bot, OWNER_CHAT, "/start")
    say(bot, OWNER_CHAT, "/refresh")
    assert bot.redis.jobs == [("enqueue_collection",)]


def test_modes_help_and_unknown(bot):
    say(bot, OWNER_CHAT, "/start")
    say(bot, OWNER_CHAT, "/modes")
    assert "/f1" in bot.telegram.sent[-1][1]
    say(bot, OWNER_CHAT, "/help")
    assert "/refresh" in bot.telegram.sent[-1][1]
    say(bot, OWNER_CHAT, "/nope")
    assert "Unknown command" in bot.telegram.sent[-1][1]


def test_plain_text_is_ignored(bot):
    say(bot, OWNER_CHAT, "/start")
    bot.telegram.sent.clear()
    say(bot, OWNER_CHAT, "hello")
    assert bot.telegram.sent == []
