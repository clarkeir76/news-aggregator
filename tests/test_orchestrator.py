"""Tests for the orchestration pipeline"""

import pytest
from datetime import datetime
from pathlib import Path
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


def make_aggregator(feed_config_file, **kwargs):
    defaults = dict(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        enable_slack=False,
        enable_summarization=False,
        enable_llm_classification=False,
        max_concurrent_feeds=1,
    )
    defaults.update(kwargs)
    return NewsAggregator(**defaults)


# --- Initialisation ---


def test_no_store_when_persistence_disabled(feed_config_file):
    assert make_aggregator(feed_config_file).store is None


def test_no_notifier_when_slack_disabled(feed_config_file):
    assert make_aggregator(feed_config_file).notifier is None


def test_no_notifier_when_no_webhooks(feed_config_file):
    assert (
        make_aggregator(
            feed_config_file, enable_slack=True, slack_webhooks=None
        ).notifier
        is None
    )


def test_no_summarizer_when_disabled(feed_config_file):
    assert (
        make_aggregator(
            feed_config_file, enable_summarization=False, openai_api_key="key"
        ).summarizer
        is None
    )


def test_no_summarizer_when_no_key(feed_config_file):
    assert (
        make_aggregator(
            feed_config_file, enable_summarization=True, openai_api_key=None
        ).summarizer
        is None
    )


def test_notifier_created_when_slack_enabled(feed_config_file):
    agg = make_aggregator(
        feed_config_file, enable_slack=True, slack_webhooks={"tech": "https://x"}
    )
    assert agg.notifier is not None


def test_uses_llm_classifier_when_enabled_with_key(feed_config_file, mocker):
    from unittest.mock import MagicMock

    mocker.patch("app.src.classification.openai.OpenAI", return_value=MagicMock())
    agg = make_aggregator(
        feed_config_file, enable_llm_classification=True, openai_api_key="key"
    )
    from app.src.classification import LLMClassifier

    assert isinstance(agg.classifier, LLMClassifier)


def test_uses_keyword_classifier_when_llm_disabled(feed_config_file):
    from app.src.classification import KeywordClassifier

    agg = make_aggregator(feed_config_file, enable_llm_classification=False)
    assert isinstance(agg.classifier, KeywordClassifier)


# --- Pipeline ---


def test_run_returns_stats(mocker, feed_config_file, article):
    agg = make_aggregator(feed_config_file)
    mocker.patch.object(
        agg.ingester,
        "ingest_feeds",
        return_value=(
            [article],
            {
                "total_feeds": 1,
                "successful_feeds": 1,
                "failed_feeds": 0,
                "total_articles": 1,
                "total_errors": 0,
            },
        ),
    )
    mocker.patch.object(agg.classifier, "classify_and_filter", return_value=[article])
    mocker.patch.object(agg, "_enrich_content", return_value=[article])
    mocker.patch.object(
        agg.deduplicator,
        "deduplicate",
        return_value=(
            [article],
            {
                "total_input": 1,
                "url_duplicates": 0,
                "content_hash_duplicates": 0,
                "title_fuzzy_duplicates": 0,
                "unique_output": 1,
            },
        ),
    )

    stats = agg.run()
    assert stats["errors"] == []
    assert stats["articles_classified"] == 1


def test_run_handles_pipeline_error(mocker, feed_config_file):
    agg = make_aggregator(feed_config_file)
    mocker.patch.object(
        agg.ingester, "ingest_feeds", side_effect=RuntimeError("feed error")
    )

    stats = agg.run()
    assert len(stats["errors"]) == 1
    assert "feed error" in stats["errors"][0]


def test_run_skips_slack_when_no_new_articles(mocker, feed_config_file):
    agg = make_aggregator(
        feed_config_file,
        enable_slack=True,
        slack_webhooks={"tech": "https://x"},
    )
    mocker.patch.object(
        agg.ingester,
        "ingest_feeds",
        return_value=(
            [],
            {
                "total_feeds": 1,
                "successful_feeds": 0,
                "failed_feeds": 1,
                "total_articles": 0,
                "total_errors": 0,
            },
        ),
    )
    mocker.patch.object(agg.classifier, "classify_and_filter", return_value=[])
    mocker.patch.object(agg, "_enrich_content", return_value=[])
    mocker.patch.object(
        agg.deduplicator,
        "deduplicate",
        return_value=(
            [],
            {
                "total_input": 0,
                "url_duplicates": 0,
                "content_hash_duplicates": 0,
                "title_fuzzy_duplicates": 0,
                "unique_output": 0,
            },
        ),
    )
    mock_notify = mocker.patch.object(agg.notifier, "notify_digest")

    agg.run()
    mock_notify.assert_not_called()


def test_enrich_content_fetches_for_all_articles(mocker, feed_config_file, article):
    agg = make_aggregator(feed_config_file)
    mocker.patch.object(
        agg.content_extractor, "get_content", return_value="Full article text"
    )

    result = agg._enrich_content([article])

    assert len(result) == 1
    assert result[0].content == "Full article text"


def test_enrich_content_handles_fetch_failure(mocker, feed_config_file, article):
    original_content = article.content
    agg = make_aggregator(feed_config_file)
    mocker.patch.object(
        agg.content_extractor, "get_content", side_effect=Exception("fetch failed")
    )

    result = agg._enrich_content([article])

    assert len(result) == 1
    assert result[0].url == article.url
    assert (
        result[0].content == original_content
    )  # original content preserved on failure


def test_summarise_runs_concurrently(mocker, feed_config_file, article):
    from unittest.mock import MagicMock

    mocker.patch("app.src.summarization.openai.OpenAI", return_value=MagicMock())
    agg = make_aggregator(
        feed_config_file,
        enable_summarization=True,
        openai_api_key="test-key",
        max_concurrent_summarizations=3,
    )
    mocker.patch.object(agg.summarizer, "summarize", return_value="A summary.")

    summaries = agg._summarise([(article, None)])

    assert article.url in summaries
    assert summaries[article.url] == "A summary."
    assert agg.stats["articles_summarized"] == 1


def test_cutoff_uses_last_run_when_more_recent(tmp_path, feed_config_file):
    """If last run was 1 hour ago, cutoff should be 1 hour ago (not 24 hours)."""
    from datetime import datetime, timedelta, timezone

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    last_run_file = str(tmp_path / ".last_run")
    Path(last_run_file).write_text(one_hour_ago.isoformat())

    agg = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        max_article_age_hours=24,
        last_run_file=last_run_file,
    )
    cutoff = agg.ingester.cutoff
    assert cutoff is not None
    twenty_three_hours_ago = datetime.now(timezone.utc) - timedelta(hours=23)
    assert cutoff > twenty_three_hours_ago  # closer to 1h ago than 24h ago


def test_cutoff_caps_at_max_age_when_last_run_older(tmp_path, feed_config_file):
    """If last run was 3 days ago, cutoff should be capped at max_article_age_hours."""
    from datetime import datetime, timedelta, timezone

    three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
    last_run_file = str(tmp_path / ".last_run")
    Path(last_run_file).write_text(three_days_ago.isoformat())

    agg = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        max_article_age_hours=24,
        last_run_file=last_run_file,
    )
    cutoff = agg.ingester.cutoff
    assert cutoff is not None
    twenty_five_hours_ago = datetime.now(timezone.utc) - timedelta(hours=25)
    assert cutoff > twenty_five_hours_ago  # within the last 24 hours


def test_save_last_run_writes_file(tmp_path, feed_config_file):
    from pathlib import Path

    last_run_file = str(tmp_path / ".last_run")
    agg = NewsAggregator(
        feed_config_path=feed_config_file,
        enable_persistence=False,
        last_run_file=last_run_file,
    )
    agg._save_last_run()
    assert Path(last_run_file).exists()


def test_summarise_handles_failure_gracefully(mocker, feed_config_file, article):
    from unittest.mock import MagicMock

    mocker.patch("app.src.summarization.openai.OpenAI", return_value=MagicMock())
    agg = make_aggregator(
        feed_config_file,
        enable_summarization=True,
        openai_api_key="test-key",
    )
    mocker.patch.object(agg.summarizer, "summarize", side_effect=Exception("API error"))

    summaries = agg._summarise([(article, None)])

    assert summaries == {}
    assert agg.stats["articles_summarized"] == 0
