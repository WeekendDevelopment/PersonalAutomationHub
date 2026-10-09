"""Optional AI briefing through any OpenAI-compatible endpoint.

Configured purely by env vars (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL). When they
are unset, or the call fails for any reason, the digest simply has no briefing.
"""

import logging

import httpx

from .config import Settings
from .models import Item

log = logging.getLogger(__name__)

PROMPT = (
    "You write the opening of a personal news digest about {topic}. "
    "Using only the headlines below, write a 2-3 sentence briefing of the main "
    "themes. Plain text only: no markdown, no lists, no preamble.\n\n{headlines}"
)


async def briefing(settings: Settings, topic: str, items: list[Item]) -> str | None:
    if not (settings.llm_base_url and settings.llm_model and items):
        return None
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"} if settings.llm_api_key else {}
    body = {
        "model": settings.llm_model,
        "temperature": 0.3,
        "messages": [
            {
                "role": "user",
                "content": PROMPT.format(
                    topic=topic, headlines="\n".join(f"- {i.title}" for i in items)
                ),
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.llm_base_url}/chat/completions", json=body, headers=headers
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
        return text.strip() or None
    except Exception as error:  # the briefing is a nice-to-have: never fail the digest
        log.warning("LLM briefing skipped: %s", type(error).__name__)
        return None
