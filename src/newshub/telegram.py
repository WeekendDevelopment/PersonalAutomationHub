"""A tiny Telegram Bot API client - just the four calls newshub needs."""

import logging

import httpx

# httpx logs every request URL at INFO level, and Telegram URLs contain the
# bot token. Keep it out of the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

POLL_SECONDS = 50


class TelegramError(Exception):
    pass


class Telegram:
    def __init__(self, token: str):
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}/", timeout=POLL_SECONDS + 20
        )

    async def call(self, method: str, **params):
        try:
            response = await self._client.post(method, json=params)
        except httpx.HTTPError as error:
            # Do not chain the httpx error: its message includes the token URL.
            raise TelegramError(f"{method}: {type(error).__name__}") from None
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(f"{method}: {data.get('description')}")
        return data["result"]

    async def send(self, chat_id: int, html: str) -> None:
        await self.call(
            "sendMessage",
            chat_id=chat_id,
            text=html,
            parse_mode="HTML",
            link_preview_options={"is_disabled": True},
        )

    async def get_updates(self, offset: int | None) -> list[dict]:
        """Long polling: waits up to POLL_SECONDS for new messages."""
        return await self.call(
            "getUpdates", offset=offset, timeout=POLL_SECONDS, allowed_updates=["message"]
        )

    async def set_commands(self, commands: dict[str, str]) -> None:
        """Fill the bot's "/" menu in the Telegram app."""
        await self.call(
            "setMyCommands",
            commands=[{"command": c, "description": d} for c, d in commands.items()],
        )

    async def close(self) -> None:
        await self._client.aclose()
