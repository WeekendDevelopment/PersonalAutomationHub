"""Command line tools that need no database, Redis or Telegram.

    python -m newshub.cli preview <mode>   fetch, score and print a digest
    python -m newshub.cli check            test every source in modes.yaml
"""

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from . import pipeline, sources
from .config import Config, Mode, load_config
from .digest import age


async def _collect(mode: Mode):
    """Fetch all of a mode's sources at once. Returns (source, items-or-error) pairs."""
    async with sources.http_client() as client:
        results = await asyncio.gather(
            *(pipeline.collect_source(client, mode, source) for source in mode.sources),
            return_exceptions=True,
        )
    return list(zip(mode.sources, results))


async def preview(config: Config, mode_name: str, limit: int | None) -> int:
    mode = config.modes.get(mode_name)
    if mode is None:
        print(f"Unknown mode {mode_name!r}. Available: {', '.join(config.modes)}")
        return 2

    items = []
    for source, result in await _collect(mode):
        if isinstance(result, Exception):
            print(f"! {source.name}: fetch failed ({result!r})")
        else:
            items.extend(result)

    now = datetime.now(timezone.utc)
    top = pipeline.rank(items)[: limit or mode.digest_size]
    print(f"\n{mode.emoji} {mode.title} digest - top {len(top)} of {len(items)} items\n")
    for number, item in enumerate(top, start=1):
        meta = " · ".join(p for p in (item.source, age(item.published_at, now)) if p)
        print(f"{number:>2}. [{item.score:5.1f}] {item.title}")
        print(f"             {meta}")
        print(f"             {item.url}")
    return 0


async def check(config: Config) -> int:
    """Fetch every source unfiltered: does it respond, and does it parse?"""
    failures = 0
    async with sources.http_client() as client:
        for mode in config.modes.values():
            print(f"\n{mode.emoji} {mode.name}")
            results = await asyncio.gather(
                *(sources.fetch(client, source) for source in mode.sources),
                return_exceptions=True,
            )
            for source, result in zip(mode.sources, results):
                if isinstance(result, Exception):
                    failures += 1
                    print(f"  FAIL  {source.name}: {result!r}")
                elif not result:
                    failures += 1
                    print(f"  EMPTY {source.name}: responded, but no items parsed")
                else:
                    dated = sum(1 for item in result if item.published_at)
                    print(f"  ok    {source.name}: {len(result)} items ({dated} with a date)")
    return 1 if failures else 0


def main() -> int:
    # Windows consoles default to a legacy encoding that cannot print emoji.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(prog="newshub")
    parser.add_argument("--config", help="path to modes.yaml (default: config/modes.yaml)")
    commands = parser.add_subparsers(dest="command", required=True)
    preview_cmd = commands.add_parser("preview", help="fetch, score and print a digest")
    preview_cmd.add_argument("mode")
    preview_cmd.add_argument("--limit", type=int, help="number of items (default: digest_size)")
    commands.add_parser("check", help="test every source in modes.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.command == "preview":
        return asyncio.run(preview(config, args.mode, args.limit))
    return asyncio.run(check(config))


if __name__ == "__main__":
    sys.exit(main())
