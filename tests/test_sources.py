"""Adapter parsing tests. They feed canned content to parse(): no network."""

from datetime import datetime, timezone

from newshub.sources import hackernews, rss

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>First &amp; best</title>
      <link>https://example.com/1</link>
      <description>&lt;p&gt;Some &lt;b&gt;bold&lt;/b&gt;   text&lt;/p&gt;</description>
      <pubDate>Fri, 09 Oct 2026 10:30:00 +0100</pubDate>
    </item>
    <item>
      <title>No date</title>
      <link>https://example.com/2</link>
    </item>
    <item>
      <title>No link, so it is skipped</title>
    </item>
  </channel>
</rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example</title>
  <entry>
    <title>Atom entry</title>
    <link href="https://example.com/atom"/>
    <updated>2026-10-09T08:00:00Z</updated>
    <summary>Short summary</summary>
  </entry>
</feed>"""


def test_rss_parses_title_link_and_cleans_summary():
    items = rss.parse(RSS, "Example")
    assert [i.title for i in items] == ["First & best", "No date"]
    first = items[0]
    assert first.url == "https://example.com/1"
    assert first.source == "Example"
    assert first.summary == "Some bold text"


def test_rss_dates_are_converted_to_utc():
    first, second = rss.parse(RSS, "Example")
    assert first.published_at == datetime(2026, 10, 9, 9, 30, tzinfo=timezone.utc)
    assert second.published_at is None


def test_atom_is_supported():
    (entry,) = rss.parse(ATOM, "Example")
    assert entry.title == "Atom entry"
    assert entry.url == "https://example.com/atom"
    assert entry.published_at == datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)


def test_rss_garbage_gives_no_items():
    assert rss.parse("this is not a feed", "Example") == []


def test_hackernews_parse():
    data = {
        "hits": [
            {
                "objectID": "1",
                "title": "Show HN: a thing",
                "url": "https://example.com/thing",
                "points": 250,
                "created_at_i": 1791535800,
            },
            {"objectID": "2", "title": "Ask HN: no url?", "url": None, "points": None},
            {"objectID": "3", "title": ""},
        ]
    }
    first, second = hackernews.parse(data, "Hacker News")
    assert first.url == "https://example.com/thing"
    assert first.popularity == 250
    assert first.published_at == datetime.fromtimestamp(1791535800, timezone.utc)
    assert second.url == "https://news.ycombinator.com/item?id=2"
    assert second.popularity == 0
    assert second.published_at is None
