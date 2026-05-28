"""Tests for the orchestration pipeline"""

import pytest
from datetime import datetime
from app.src.models import Article
from app.src.orchestrator import NewsAggregator


@pytest.fixture
def article():
    return Article(
        title="Test Article",
        source="example.com",
        url="https://example.com/article",
        published_at=datetime.utcnow(),
        content="A" * 300,
        topics=["tech"],
    )


@pytest.fixture
def feed_config_file(tmp_path):
    config = tmp_path / "feeds.yaml"
    config.write_text("feeds:\n  - url: 'https://example.com/rss'\n")
    return str(config)


# --- Initialisation ---

def test_no_store_when_persistence_disabled(feed_config_file):
    aggregator = NewsAggregator(feed_config_path=feed_config_file, enable_persistence=False)
    assert aggregator.store is None


def test_no_notifier_when_slack_disabled(feed_config_file):
    aggregator = NewsAggregator(feed_config_path=feed_config_file, enable_slack=False)
    assert aggregator.notifier is None


def test_no_notifier_when_no_webhooks_provided(feed_config_file):
    aggregator = NewsAggregator(feed_config_path=feed_config_file, enable_slack=True, slack_webhooks=None)
    assert aggregator.notifier is None


def test_no_summarizer_when_summarization_disabled(feed_config_file):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_summarization=False,
        openai_api_key="key",
    )
    assert aggregator.summarizer is None


def test_no_summarizer_when_no_api_key(feed_config_file):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_summarization=True,
        openai_api_key=None,
    )
    assert aggregator.summarizer is None


def test_notifier_created_when_slack_enabled(feed_config_file):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_slack=True,
        slack_webhooks={"tech": "https://hooks.slack.com/x"},
    )
    assert aggregator.notifier is not None


# --- Pipeline ---

def test_run_returns_stats(mocker, feed_config_file, article):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        enable_slack=False,
        enable_summarization=False,
    )
    mocker.patch.object(aggregator.ingester, "ingest_feeds", return_value=(
        [article],
        {"total_feeds": 1, "successful_feeds": 1, "failed_feeds": 0, "total_articles": 1, "total_errors": 0},
    ))
    mocker.patch.object(aggregator.classifier, "classify_articles", return_value=[article])
    mocker.patch.object(aggregator.deduplicator, "deduplicate", return_value=(
        [article],
        {"total_input": 1, "url_duplicates": 0, "content_hash_duplicates": 0, "title_fuzzy_duplicates": 0, "unique_output": 1},
    ))

    stats = aggregator.run()

    assert stats["errors"] == []
    assert stats["unique_output"] == 1


def test_run_handles_pipeline_error_gracefully(mocker, feed_config_file):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        enable_slack=False,
        enable_summarization=False,
    )
    mocker.patch.object(aggregator.ingester, "ingest_feeds", side_effect=RuntimeError("feed error"))

    stats = aggregator.run()

    assert len(stats["errors"]) == 1
    assert "feed error" in stats["errors"][0]


def test_run_skips_slack_when_no_new_articles(mocker, feed_config_file):
    aggregator = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        enable_slack=True,
        slack_webhooks={"tech": "https://hooks.slack.com/x"},
        enable_summarization=False,
    )
    mocker.patch.object(aggregator.ingester, "ingest_feeds", return_value=(
        [],
        {"total_feeds": 1, "successful_feeds": 1, "failed_feeds": 0, "total_articles": 0, "total_errors": 0},
    ))
    mocker.patch.object(aggregator.classifier, "classify_articles", return_value=[])
    mocker.patch.object(aggregator.deduplicator, "deduplicate", return_value=(
        [],
        {"total_input": 0, "url_duplicates": 0, "content_hash_duplicates": 0, "title_fuzzy_duplicates": 0, "unique_output": 0},
    ))
    mock_notify = mocker.patch.object(aggregator.notifier, "notify_digest")

    aggregator.run()

    mock_notify.assert_not_called()
