"""Tests for RSS feed ingestion"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from app.src.ingestion import FeedConfig, RSSIngester
from app.src.models import Article


# --- FeedConfig ---

def test_feed_config_load_from_yaml(tmp_path):
    config_file = tmp_path / "feeds.yaml"
    config_file.write_text("feeds:\n  - url: 'https://a.com/rss'\n  - url: 'https://b.com/feed'\n")

    configs = FeedConfig.load_from_yaml(str(config_file))

    assert len(configs) == 2
    assert configs[0].url == "https://a.com/rss"
    assert configs[1].url == "https://b.com/feed"


def test_feed_config_load_missing_file():
    configs = FeedConfig.load_from_yaml("/nonexistent/feeds.yaml")
    assert configs == []


def test_feed_config_load_invalid_yaml(tmp_path):
    config_file = tmp_path / "feeds.yaml"
    config_file.write_text("feeds: [invalid: yaml: {")

    configs = FeedConfig.load_from_yaml(str(config_file))
    assert configs == []


# --- RSSIngester._parse_date ---

def test_parse_date_from_published_parsed():
    entry = {"published_parsed": (2024, 1, 15, 10, 30, 0, 0, 0, 0)}
    date = RSSIngester._parse_date(entry)
    assert date == datetime(2024, 1, 15, 10, 30, 0)


def test_parse_date_falls_back_to_updated_parsed():
    entry = {"updated_parsed": (2024, 3, 20, 12, 0, 0, 0, 0, 0)}
    date = RSSIngester._parse_date(entry)
    assert date == datetime(2024, 3, 20, 12, 0, 0)


def test_parse_date_falls_back_to_utcnow():
    before = datetime.utcnow()
    date = RSSIngester._parse_date({})
    after = datetime.utcnow()
    assert before <= date <= after


def test_age_filter_rejects_old_articles(mocker):
    from datetime import timezone
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [{
        "title": "Old Article",
        "link": "https://example.com/old",
        "summary": "Old news",
        "published_parsed": (2020, 1, 1, 0, 0, 0, 0, 0, 0),
    }]
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    from datetime import datetime, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    ingester = RSSIngester(cutoff=cutoff)
    articles, _ = ingester.ingest_feed("https://example.com/rss")
    assert len(articles) == 0


def test_age_filter_accepts_recent_articles(mocker):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [{
        "title": "Fresh Article",
        "link": "https://example.com/fresh",
        "summary": "A" * 50,
        "published_parsed": (2099, 1, 1, 0, 0, 0, 0, 0, 0),
    }]
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    ingester = RSSIngester(cutoff=cutoff)
    articles, _ = ingester.ingest_feed("https://example.com/rss")
    assert len(articles) == 1


def test_age_filter_disabled_when_no_cutoff(mocker):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [{
        "title": "Old Article",
        "link": "https://example.com/old",
        "summary": "Old news",
        "published_parsed": (2020, 1, 1, 0, 0, 0, 0, 0, 0),
    }]
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    ingester = RSSIngester(cutoff=None)
    articles, _ = ingester.ingest_feed("https://example.com/rss")
    assert len(articles) == 1


# --- RSSIngester._extract_rss_content ---

def test_extract_rss_content_prefers_content_over_summary():
    entry = {
        "content": [MagicMock(value="Full article body")],
        "summary": "Short summary",
    }
    assert RSSIngester._extract_rss_content(entry) == "Full article body"


def test_extract_rss_content_falls_back_to_summary():
    entry = {"summary": "Short summary"}
    assert RSSIngester._extract_rss_content(entry) == "Short summary"


def test_extract_rss_content_returns_empty_when_absent():
    assert RSSIngester._extract_rss_content({}) == ""


# --- RSSIngester.ingest_feed ---

def test_ingest_feed_returns_articles(mocker):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [{
        "title": "Test Article",
        "link": "https://example.com/article",
        "summary": "A" * 250,
        "published_parsed": (2024, 1, 15, 10, 0, 0, 0, 0, 0),
    }]
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    ingester = RSSIngester(cutoff=None)  # disable age filter for this test
    articles, errors = ingester.ingest_feed("https://example.com/rss")

    assert len(articles) == 1
    assert articles[0].title == "Test Article"
    assert errors == 0


def test_ingest_feed_returns_error_on_empty_feed(mocker):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = []
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    ingester = RSSIngester()
    articles, errors = ingester.ingest_feed("https://example.com/rss")

    assert articles == []
    assert errors == 1


def test_ingest_feed_returns_error_on_exception(mocker):
    mocker.patch("app.src.ingestion.feedparser.parse", side_effect=Exception("connection error"))

    ingester = RSSIngester()
    articles, errors = ingester.ingest_feed("https://example.com/rss")

    assert articles == []
    assert errors == 1


def test_ingest_feed_skips_entries_without_title(mocker):
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = [
        {"title": "", "link": "https://example.com/1", "summary": "A" * 250},
        {"title": "Valid Article", "link": "https://example.com/2", "summary": "A" * 250},
    ]
    mocker.patch("app.src.ingestion.feedparser.parse", return_value=mock_feed)

    ingester = RSSIngester(cutoff=None)
    articles, errors = ingester.ingest_feed("https://example.com/rss")

    assert len(articles) == 1
    assert articles[0].title == "Valid Article"


# --- RSSIngester.ingest_feeds ---

def test_ingest_feeds_aggregates_stats(mocker):
    # max_concurrent_feeds=1 keeps execution sequential so side_effect order is deterministic
    ingester = RSSIngester(max_concurrent_feeds=1, cutoff=None)
    mocker.patch.object(ingester, "ingest_feed", side_effect=[
        ([MagicMock(), MagicMock()], 0),
        ([MagicMock()], 1),
    ])

    configs = [FeedConfig("https://a.com/rss"), FeedConfig("https://b.com/rss")]
    articles, stats = ingester.ingest_feeds(configs)

    assert stats["total_feeds"] == 2
    assert stats["total_articles"] == 3
    assert stats["successful_feeds"] == 1
    assert stats["failed_feeds"] == 1
    assert len(articles) == 3


def test_ingest_feeds_runs_concurrently(mocker):
    """Feeds should be fetched in parallel — all results collected regardless of order."""
    import time

    def slow_ingest(url):
        time.sleep(0.05)
        return ([MagicMock()], 0)

    ingester = RSSIngester(max_concurrent_feeds=5)
    mocker.patch.object(ingester, "ingest_feed", side_effect=slow_ingest)

    configs = [FeedConfig(f"https://feed{i}.com/rss") for i in range(5)]

    start = time.time()
    articles, stats = ingester.ingest_feeds(configs)
    elapsed = time.time() - start

    # 5 feeds × 50ms each = 250ms sequentially; concurrent should finish in ~50-100ms
    assert elapsed < 0.2, f"Expected concurrent execution but took {elapsed:.2f}s"
    assert stats["total_feeds"] == 5
    assert stats["total_articles"] == 5
