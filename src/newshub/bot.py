"""Telegram bot: answers commands using long polling (no public URL needed).

Run with:  python -m newshub.bot
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from html import escape

import asyncpg
from arq.connections import ArqRedis

from . import db, delivery, jobs
from .config import Config, Settings, load_config
from .telegram import Telegram

log = logging.getLogger("newshub.bot")


@dataclass
class Bot:
    settings: Settings
    config: Config
    pool: asyncpg.Pool
    redis: ArqRedis
    telegram: Telegram

    def commands(self) -> dict[str, str]:
        commands = {m.name: f"{m.emoji} {m.title} digest now" for m in self.config.modes.values()}
        commands |= {
            "modes": "List modes and their digest times",
            "refresh": "Collect news now",
            "help": "Show this help",
        }
        return commands

    def help_text(self) -> str:
        return "\n".join(f"/{name} - {escape(text)}" for name, text in self.commands().items())

    def modes_text(self) -> str:
        lines = [f"<b>Modes</b> (times are {escape(self.config.timezone)})"]
        for mode in self.config.modes.values():
            times = ", ".join(mode.digest_times) or "on demand only"
            lines.append(f"{mode.emoji} /{mode.name} - {escape(mode.title)}: {times}")
        return "\n".join(lines)

    async def handle(self, message: dict) -> None:
        text = (message.get("text") or "").strip()
        if not text.startswith("/"):
            return
        chat = message["chat"]
        chat_id = chat["id"]
        # "/tech@my_bot extra words" -> "tech"
        command = text.split()[0][1:].split("@")[0].lower()

        if command == "start":
            name = chat.get("first_name") or chat.get("title") or ""
            if await db.claim_owner(self.pool, chat_id, name):
                log.info("chat %s is now the owner", chat_id)
                await self.telegram.send(
                    chat_id, "👋 You are now the owner of this newshub.\n\n" + self.help_text()
                )
                return

        subscriber = await db.get_subscriber(self.pool, chat_id)
        if subscriber is None:
            log.info("ignored message from unknown chat %s", chat_id)
            return

        if command in ("start", "help"):
            await self.telegram.send(chat_id, self.help_text())
        elif command == "modes":
            await self.telegram.send(chat_id, self.modes_text())
        elif command == "refresh":
            await self.redis.enqueue_job(jobs.COLLECT_ALL)
            await self.telegram.send(chat_id, "🔄 Collecting now. Ask for a digest in a minute.")
        elif command in self.config.modes:
            mode = self.config.modes[command]
            sent = await delivery.send_digest(
                self.pool, self.telegram, self.settings, self.config.tz, mode, subscriber
            )
            if sent == 0:
                await self.telegram.send(
                    chat_id, f"{mode.emoji} Nothing new in {escape(mode.title)}. Try /refresh."
                )
        else:
            await self.telegram.send(chat_id, "Unknown command. See /help.")

    async def run(self) -> None:
        await self.telegram.set_commands(self.commands())
        log.info("bot started, polling for messages")
        offset = None
        while True:
            try:
                updates = await self.telegram.get_updates(offset)
            except Exception as error:
                log.warning("polling failed (%s), retrying in 5s", error)
                await asyncio.sleep(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    if "message" in update:
                        await self.handle(update["message"])
                except Exception:
                    log.exception("failed to handle update %s", update["update_id"])


async def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    settings = Settings.from_env()
    if not settings.telegram_token:
        # Stay alive instead of crash-looping, so the rest of the stack is usable.
        log.warning("TELEGRAM_BOT_TOKEN is not set: bot is idle. Set it in .env and restart.")
        await asyncio.Event().wait()
    bot = Bot(
        settings=settings,
        config=load_config(),
        pool=await db.connect(settings.database_url),
        redis=await jobs.connect(settings.redis_url),
        telegram=Telegram(settings.telegram_token),
    )
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
