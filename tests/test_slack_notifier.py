"""Tests for Slack digest notifications"""

import pytest
import requests
from datetime import datetime
from app.src.models import Article
from app.src.slack_notifier import SlackNotifier


@pytest.fixture
def article():
    return Article(
        title="Test Article",
        source="example.com",
        url="https://example.com/article",
        published_at=datetime(2024, 1, 15, 10, 0, 0),
        content="Test content",
        topics=["tech"],
    )


@pytest.fixture
def notifier():
    return SlackNotifier(
        {"tech": "https://hooks.slack.com/tech", "ai": "https://hooks.slack.com/ai"}
    )


# --- _build_digest ---


def test_build_digest_uses_payload_key(article):
    message = SlackNotifier._build_digest("tech", [article], {})
    assert "payload" in message


def test_build_digest_contains_topic_and_count(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert "Tech Digest" in payload
    assert "1 new article" in payload


def test_build_digest_singular_vs_plural():
    articles = [
        Article(
            title=f"Article {i}",
            source="s.com",
            url=f"https://s.com/{i}",
            published_at=datetime.utcnow(),
            content="x",
            topics=["tech"],
        )
        for i in range(3)
    ]
    payload = SlackNotifier._build_digest("tech", articles, {})["payload"]
    assert "3 new articles" in payload


def test_build_digest_includes_title_and_url(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert article.title in payload
    assert article.url in payload


def test_build_digest_includes_summary(article):
    summaries = {article.url: "A concise summary."}
    payload = SlackNotifier._build_digest("tech", [article], summaries)["payload"]
    assert "A concise summary." in payload


def test_build_digest_source_is_below_summary(article):
    summaries = {article.url: "A concise summary."}
    payload = SlackNotifier._build_digest("tech", [article], summaries)["payload"]
    assert payload.index("A concise summary.") < payload.index("source:")


def test_build_digest_topic_label_formats_underscore():
    article = Article(
        title="Article",
        source="s.com",
        url="https://s.com/1",
        published_at=datetime.utcnow(),
        content="x",
        topics=["cyber_security"],
    )
    payload = SlackNotifier._build_digest("cyber_security", [article], {})["payload"]
    assert "Cyber Security Digest" in payload


def test_build_digest_caps_at_max_articles():
    """More than MAX_ARTICLES articles should be capped with an 'and N more' notice."""
    articles = [
        Article(
            title=f"Article {i}",
            source="s.com",
            url=f"https://s.com/{i}",
            published_at=datetime.utcnow(),
            content="x",
            topics=["tech"],
        )
        for i in range(SlackNotifier.MAX_ARTICLES + 5)
    ]
    payload = SlackNotifier._build_digest("tech", articles, {})["payload"]

    # Header count still shows total, not capped count
    assert f"{SlackNotifier.MAX_ARTICLES + 5} new articles" in payload
    # Overflow notice present
    assert "5 more article(s) not shown" in payload
    # Only MAX_ARTICLES articles included
    assert payload.count("https://s.com/") == SlackNotifier.MAX_ARTICLES


def test_build_digest_truncates_at_max_chars():
    """Payload exceeding MAX_PAYLOAD_CHARS should be truncated with a notice."""
    articles = [
        Article(
            title=f"Article with a very long title number {i} that takes up space",
            source="s.com",
            url=f"https://s.com/{i}",
            published_at=datetime.utcnow(),
            content="x",
            topics=["tech"],
        )
        for i in range(5)
    ]
    long_summary = "A " * 1000  # 2000 chars per article
    summaries = {f"https://s.com/{i}": long_summary for i in range(5)}

    payload = SlackNotifier._build_digest("tech", articles, summaries)["payload"]

    assert len(payload) <= SlackNotifier.MAX_PAYLOAD_CHARS
    assert "truncated" in payload


# --- notify_digest ---


def test_notify_digest_sends_one_message_per_topic(mocker, notifier):
    mock_send = mocker.patch.object(SlackNotifier, "_send_webhook", return_value=True)
    articles = [
        Article(
            title="Tech",
            source="t.com",
            url="https://t.com/1",
            published_at=datetime.utcnow(),
            content="x",
            topics=["tech"],
        ),
        Article(
            title="AI",
            source="a.com",
            url="https://a.com/1",
            published_at=datetime.utcnow(),
            content="x",
            topics=["ai"],
        ),
    ]
    notifier.notify_digest(articles)
    assert mock_send.call_count == 2


def test_notify_digest_skips_topics_without_webhook(mocker, notifier):
    mock_send = mocker.patch.object(SlackNotifier, "_send_webhook", return_value=True)
    articles = [
        Article(
            title="Edu",
            source="e.com",
            url="https://e.com/1",
            published_at=datetime.utcnow(),
            content="x",
            topics=["education"],
        ),
    ]
    notifier.notify_digest(articles)
    mock_send.assert_not_called()


def test_notify_digest_returns_true_on_success(mocker, notifier, article):
    mocker.patch.object(SlackNotifier, "_send_webhook", return_value=True)
    assert notifier.notify_digest([article]) is True


def test_notify_digest_returns_false_on_webhook_failure(mocker, notifier, article):
    mocker.patch.object(SlackNotifier, "_send_webhook", return_value=False)
    assert notifier.notify_digest([article]) is False


def test_notify_digest_returns_true_when_no_matching_topics(notifier):
    articles = [
        Article(
            title="Edu",
            source="e.com",
            url="https://e.com/1",
            published_at=datetime.utcnow(),
            content="x",
            topics=["education"],
        ),
    ]
    assert notifier.notify_digest(articles) is True


# --- _send_webhook ---


def test_send_webhook_returns_true_on_200(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mocker.patch("app.src.slack_notifier.requests.post", return_value=mock_resp)
    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {}) is True


def test_send_webhook_returns_false_on_non_200(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    mocker.patch("app.src.slack_notifier.requests.post", return_value=mock_resp)
    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {}) is False


def test_send_webhook_returns_false_on_request_exception(mocker):
    mocker.patch(
        "app.src.slack_notifier.requests.post",
        side_effect=requests.RequestException("timeout"),
    )
    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {}) is False


def _scored(title, url, significance, **kwargs):
    return Article(
        title=title,
        source="s.com",
        url=url,
        published_at=datetime(2024, 1, 15, 10, 0, 0),
        content="x",
        topics=["ai"],
        significance=significance,
        **kwargs,
    )


def test_build_digest_orders_by_significance():
    articles = [
        _scored("Minor", "https://s.com/minor", 4),
        _scored("Major", "https://s.com/major", 5),
        _scored("Unscored", "https://s.com/none", None),
    ]
    payload = SlackNotifier._build_digest("ai", articles, {})["payload"]

    assert payload.index("Major") < payload.index("Minor") < payload.index("Unscored")


def test_build_digest_cap_drops_least_significant():
    articles = [
        _scored(f"Story {i}", f"https://s.com/{i}", 4)
        for i in range(SlackNotifier.MAX_ARTICLES)
    ]
    articles.append(_scored("Top story", "https://s.com/top", 5))
    payload = SlackNotifier._build_digest("ai", articles, {})["payload"]

    assert "Top story" in payload
    assert "1 more article(s) not shown" in payload


def test_build_digest_same_url_is_not_multiple_sources():
    article = _scored(
        "One article",
        "https://s.com/1",
        5,
        related_urls=["https://s.com/1"],
    )
    payload = SlackNotifier._build_digest("ai", [article], {})["payload"]

    assert payload.count("https://s.com/1") == 1
    assert "source: s.com" in payload
    assert "multiple sources" not in payload


def test_build_digest_distinct_related_urls_are_multiple_sources():
    article = _scored(
        "One story", "https://s.com/1", 5, related_urls=["https://t.com/1"]
    )
    payload = SlackNotifier._build_digest("ai", [article], {})["payload"]

    assert "https://t.com/1" in payload
    assert "source: multiple sources" in payload
