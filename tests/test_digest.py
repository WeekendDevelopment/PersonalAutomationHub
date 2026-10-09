from datetime import datetime, timedelta, timezone

from newshub.config import Mode, Source
from newshub.delivery import pick_alerts
from newshub.digest import TELEGRAM_LIMIT, age, format_alert, format_digest, split_blocks
from newshub.models import Item
from newshub.pipeline import rank

NOW = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)
MODE = Mode(
    name="f1",
    emoji="🏎️",
    title="Formula 1",
    alert_score=10,
    sources=[Source(name="Feed", url="https://example.com/feed")],
)


def item(title="Title", url="https://example.com/a", hours_old=2.0, score=1.0):
    published = NOW - timedelta(hours=hours_old) if hours_old is not None else None
    return Item(title=title, url=url, source="Feed", published_at=published, score=score)


def test_age():
    assert age(NOW - timedelta(minutes=5), NOW) == "5m ago"
    assert age(NOW - timedelta(hours=3, minutes=59), NOW) == "3h ago"
    assert age(NOW - timedelta(days=2, hours=1), NOW) == "2d ago"
    assert age(None, NOW) == ""


def test_digest_has_header_and_numbered_links():
    (message,) = format_digest(MODE, [item("One"), item("Two", url="https://example.com/b")], NOW)
    assert message.startswith("🏎️ <b>Formula 1 digest</b> · Fri 09 Oct, 18:00")
    assert '<b>1.</b> <a href="https://example.com/a">One</a>' in message
    assert '<b>2.</b> <a href="https://example.com/b">Two</a>' in message
    assert "<i>Feed · 2h ago</i>" in message


def test_digest_escapes_html():
    tricky = item('Tom & "Jerry" <script>', url='https://example.com/?a=1&b="2"')
    (message,) = format_digest(MODE, [tricky], NOW)
    assert "Tom &amp; &quot;Jerry&quot; &lt;script&gt;" in message
    assert 'href="https://example.com/?a=1&amp;b=&quot;2&quot;"' in message
    assert "<script>" not in message


def test_digest_briefing_is_included_and_escaped():
    (message,) = format_digest(MODE, [item()], NOW, briefing="Big day <b>today</b>.")
    assert "<i>Big day &lt;b&gt;today&lt;/b&gt;.</i>" in message


def test_digest_item_without_date_shows_source_only():
    (message,) = format_digest(MODE, [item(hours_old=None)], NOW)
    assert "<i>Feed</i>" in message


def test_long_digest_is_split_under_the_limit_without_losing_items():
    items = [item("T" * 190, url=f"https://example.com/{n}") for n in range(40)]
    messages = format_digest(MODE, items, NOW)
    assert len(messages) > 1
    assert all(len(message) <= TELEGRAM_LIMIT for message in messages)
    assert sum(message.count("<a href=") for message in messages) == 40
    # no item is cut in half: tags stay balanced in every message
    assert all(message.count("<a ") == message.count("</a>") for message in messages)


def test_split_blocks_packs_greedily():
    assert split_blocks(["aaaa", "bbbb", "cccc"], limit=10) == ["aaaa\n\nbbbb", "cccc"]
    assert split_blocks([], limit=10) == []


def test_alert_format():
    message = format_alert(MODE, item("Driver signs"), NOW)
    assert message.startswith("🚨 🏎️ <b>Formula 1 alert</b>\n")
    assert '<a href="https://example.com/a">Driver signs</a>' in message


def test_pick_alerts_needs_high_score_and_fresh_item():
    hot = item("hot", score=12, hours_old=1)
    stale = item("stale", score=20, hours_old=7)
    undated = item("undated", score=20, hours_old=None)
    dull = item("dull", score=9.9, hours_old=1)
    assert pick_alerts(MODE, [hot, stale, undated, dull], NOW) == [hot]


def test_pick_alerts_caps_at_three_best():
    items = [item(str(n), score=10 + n, hours_old=1) for n in range(5)]
    assert [i.title for i in pick_alerts(MODE, items, NOW)] == ["4", "3", "2"]


def test_pick_alerts_off_when_mode_has_no_alert_score():
    quiet = MODE.model_copy(update={"alert_score": None})
    assert pick_alerts(quiet, [item(score=99, hours_old=1)], NOW) == []


def test_rank_orders_by_score_then_newest_and_dedupes_urls():
    low = item("low", url="https://example.com/1", score=1)
    old = item("old", url="https://example.com/2", score=5, hours_old=9)
    new = item("new", url="https://example.com/3", score=5, hours_old=1)
    dupe = item("dupe", url="https://example.com/3", score=2)
    assert [i.title for i in rank([low, old, dupe, new])] == ["new", "old", "low"]
