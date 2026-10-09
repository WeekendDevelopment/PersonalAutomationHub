from newshub.config import Mode, Source
from newshub.models import Item
from newshub.scoring import matches, popularity_bonus, score_item

SOURCE = Source(name="Feed", url="https://example.com/feed")
BOOSTED = Source(name="Boosted", url="https://example.com/feed", boost=1.5)
MODE = Mode(
    name="tech",
    interests={"kubernetes": 4, "go": 2, "event-driven": 3},
    block=["sponsored"],
    sources=[SOURCE],
)


def item(title="", summary="", popularity=0):
    return Item(title=title, summary=summary, popularity=popularity, url="https://x", source="Feed")


def test_whole_word_match_only():
    assert matches("go", "Why Go is fast")
    assert not matches("go", "Google ships a thing")
    assert not matches("go", "It was a long time ago")


def test_match_is_case_insensitive_and_handles_punctuation():
    assert matches("kubernetes", "KUBERNETES 1.40 released")
    assert matches("event-driven", "An event-driven design")
    assert matches("c++", "Modern C++ tips")


def test_title_hit_counts_double():
    assert score_item(item(title="Kubernetes news"), MODE, SOURCE) == 8
    assert score_item(item(summary="all about kubernetes"), MODE, SOURCE) == 4


def test_keyword_in_title_and_summary_is_not_counted_twice():
    both = item(title="Kubernetes news", summary="more kubernetes")
    assert score_item(both, MODE, SOURCE) == 8


def test_scores_add_up_across_keywords():
    scored = score_item(item(title="Kubernetes in Go", summary="event-driven"), MODE, SOURCE)
    assert scored == 8 + 4 + 3


def test_no_match_scores_zero():
    assert score_item(item(title="Cooking pasta"), MODE, SOURCE) == 0


def test_block_keyword_drops_item():
    assert score_item(item(title="Kubernetes (sponsored)"), MODE, SOURCE) is None
    assert score_item(item(title="Kubernetes", summary="Sponsored post"), MODE, SOURCE) is None


def test_source_boost_is_added():
    assert score_item(item(title="Cooking pasta"), MODE, BOOSTED) == 1.5


def test_popularity_bonus_grows_slowly_and_is_capped():
    assert popularity_bonus(0) == 0
    assert 0.9 < popularity_bonus(9) <= 1.0
    assert popularity_bonus(100) < popularity_bonus(500)
    assert popularity_bonus(1_000_000) == 3.0


def test_popularity_is_added_to_score():
    assert score_item(item(title="Cooking pasta", popularity=99), MODE, SOURCE) == 2.0
