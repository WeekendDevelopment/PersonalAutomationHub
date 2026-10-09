from pathlib import Path

import pytest
from pydantic import ValidationError

from newshub.config import Settings, load_config

REPO_ROOT = Path(__file__).resolve().parents[1]

MINIMAL = """
timezone: Europe/London
modes:
  tech:
    emoji: "💻"
    interests: {kubernetes: 4, rust: 2}
    block: [sponsored]
    digest_times: ["08:00", 18:30]
    alert_score: 12
    sources:
      - name: Example
        url: https://example.com/feed
        boost: 1
      - name: HN
        type: hackernews
        options: {min_points: 100}
"""


def write(tmp_path, text):
    path = tmp_path / "modes.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_load_minimal_config(tmp_path):
    config = load_config(write(tmp_path, MINIMAL))
    assert config.timezone == "Europe/London"
    assert config.tz.key == "Europe/London"
    mode = config.modes["tech"]
    assert mode.name == "tech"
    assert mode.title == "Tech"  # defaults to the capitalised name
    assert mode.interests == {"kubernetes": 4, "rust": 2}
    assert mode.alert_score == 12
    assert mode.digest_size == 10  # default
    assert mode.sources[0].type == "rss"  # default
    assert mode.sources[0].boost == 1
    assert mode.sources[1].options == {"min_points": 100}
    assert mode.source("HN").type == "hackernews"
    assert mode.source("missing") is None


def test_unquoted_yaml_time_is_repaired(tmp_path):
    # YAML turns an unquoted 18:30 into the integer 1110.
    config = load_config(write(tmp_path, MINIMAL))
    assert config.modes["tech"].digest_times == ["08:00", "18:30"]


@pytest.mark.parametrize(
    "broken",
    [
        MINIMAL.replace("Europe/London", "Mars/Olympus"),
        MINIMAL.replace('"08:00"', '"8am"'),
        MINIMAL.replace("  tech:", "  help:"),  # reserved bot command
        MINIMAL.replace("  tech:", "  My-Mode:"),  # not a valid command name
        MINIMAL.replace("type: hackernews", "type: not-a-module"),
        "timezone: UTC\nmodes:\n  tech:\n    sources: []\n",  # a mode needs a source
    ],
)
def test_invalid_config_is_rejected(tmp_path, broken):
    with pytest.raises((ValidationError, ValueError)):
        load_config(write(tmp_path, broken))


def test_shipped_modes_file_is_valid():
    config = load_config(REPO_ROOT / "config" / "modes.yaml")
    assert config.timezone == "Europe/London"
    assert {"tech", "gaming", "f1"} <= set(config.modes)
    for mode in config.modes.values():
        assert mode.digest_times, f"{mode.name} has no digest times"
        for source in mode.sources:
            assert source.type == "hackernews" or source.url, f"{source.name} has no url"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", " abc ")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example/v1/")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    settings = Settings.from_env()
    assert settings.telegram_token == "abc"
    assert settings.llm_base_url == "https://llm.example/v1"
    assert settings.llm_model == ""
