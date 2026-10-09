"""Configuration: modes come from config/modes.yaml, secrets from env vars."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

# Bot commands that a mode may not be named after.
RESERVED_NAMES = {"start", "modes", "refresh", "help"}


class Source(BaseModel):
    name: str
    type: str = "rss"  # name of a module in newshub/sources/
    url: str | None = None
    boost: float = 0  # added to the score of every item from this source
    options: dict[str, Any] = {}  # adapter-specific, e.g. {min_points: 100}

    @field_validator("type")
    @classmethod
    def _type_is_module_name(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError(f"invalid source type {value!r}")
        return value


class Mode(BaseModel):
    name: str
    emoji: str = "📰"
    title: str = ""
    interests: dict[str, float] = {}  # keyword -> weight
    block: list[str] = []  # an item matching any of these is dropped
    sources: list[Source] = Field(min_length=1)
    digest_times: list[str] = []  # local "HH:MM"
    digest_size: int = Field(default=10, ge=1, le=50)
    alert_score: float | None = None  # None = no alerts for this mode
    max_age_hours: int = Field(default=48, ge=1)  # older items are ignored

    @field_validator("name")
    @classmethod
    def _name_is_a_command(cls, value: str) -> str:
        # The mode name doubles as a Telegram command (/tech), which limits it.
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", value):
            raise ValueError(f"mode name {value!r} must be lowercase letters, digits or _")
        if value in RESERVED_NAMES:
            raise ValueError(f"mode name {value!r} is reserved for a bot command")
        return value

    @field_validator("digest_times", mode="before")
    @classmethod
    def _normalise_times(cls, value: Any) -> Any:
        # YAML reads an unquoted 18:30 as the number 1110 (base 60). Undo that.
        times = []
        for entry in value or []:
            if isinstance(entry, int):
                entry = f"{entry // 60:02d}:{entry % 60:02d}"
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(entry)):
                raise ValueError(f"digest time {entry!r} must look like 08:00")
            times.append(entry)
        return times

    @model_validator(mode="after")
    def _default_title(self) -> "Mode":
        if not self.title:
            self.title = self.name.capitalize()
        return self

    def source(self, name: str) -> Source | None:
        return next((s for s in self.sources if s.name == name), None)


class Config(BaseModel):
    timezone: str = "UTC"
    collect_every_minutes: int = Field(default=30, ge=5, le=60)
    modes: dict[str, Mode]

    @field_validator("timezone")
    @classmethod
    def _timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception:
            raise ValueError(f"unknown timezone {value!r} (use a name like Europe/London)")
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("MODES_FILE", "config/modes.yaml"))
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    # The mode's key in the file is its name; copy it into the mode itself.
    for name, mode in (data.get("modes") or {}).items():
        mode["name"] = name
    return Config.model_validate(data)


@dataclass(frozen=True)
class Settings:
    """Secrets and connection strings, read from environment variables."""

    database_url: str
    redis_url: str
    telegram_token: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ.get
        return cls(
            database_url=env("DATABASE_URL", "postgresql://newshub:newshub@localhost:5432/newshub"),
            redis_url=env("REDIS_URL", "redis://localhost:6379"),
            telegram_token=env("TELEGRAM_BOT_TOKEN", "").strip(),
            llm_base_url=env("LLM_BASE_URL", "").strip().rstrip("/"),
            llm_api_key=env("LLM_API_KEY", "").strip(),
            llm_model=env("LLM_MODEL", "").strip(),
        )
