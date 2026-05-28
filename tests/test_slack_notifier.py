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
    return SlackNotifier({"tech": "https://hooks.slack.com/tech", "ai": "https://hooks.slack.com/ai"})


# --- _build_digest ---

def test_build_digest_contains_topic_and_count(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert "Tech Digest" in payload
    assert "1 new article" in payload


def test_build_digest_singular_vs_plural():
    articles = [
        Article(title=f"Article {i}", source="s.com", url=f"https://s.com/{i}",
                published_at=datetime.utcnow(), content="x", topics=["tech"])
        for i in range(3)
    ]
    payload = SlackNotifier._build_digest("tech", articles, {})["payload"]
    assert "3 new articles" in payload
    assert "3 new article " not in payload  # not accidentally plural-less


def test_build_digest_includes_article_title_and_source(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert article.title in payload
    assert article.source in payload


def test_build_digest_includes_summary_when_present(article):
    summaries = {article.url: "A concise summary of the article."}
    payload = SlackNotifier._build_digest("tech", [article], summaries)["payload"]
    assert "A concise summary of the article." in payload


def test_build_digest_omits_summary_when_absent(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert "A concise summary" not in payload


def test_build_digest_title_is_hyperlinked(article):
    payload = SlackNotifier._build_digest("tech", [article], {})["payload"]
    assert f"<{article.url}|{article.title}>" in payload


def test_build_digest_topic_label_formats_underscore():
    article = Article(title="Article", source="s.com", url="https://s.com/1",
                      published_at=datetime.utcnow(), content="x", topics=["cyber_security"])
    payload = SlackNotifier._build_digest("cyber_security", [article], {})["payload"]
    assert "Cyber Security Digest" in payload


# --- notify_digest ---

def test_notify_digest_sends_one_message_per_topic(mocker, notifier):
    mock_send = mocker.patch.object(SlackNotifier, "_send_webhook", return_value=True)
    articles = [
        Article(title="Tech", source="t.com", url="https://t.com/1",
                published_at=datetime.utcnow(), content="x", topics=["tech"]),
        Article(title="AI", source="a.com", url="https://a.com/1",
                published_at=datetime.utcnow(), content="x", topics=["ai"]),
    ]

    notifier.notify_digest(articles)

    assert mock_send.call_count == 2


def test_notify_digest_skips_topics_without_webhook(mocker, notifier):
    mock_send = mocker.patch.object(SlackNotifier, "_send_webhook", return_value=True)
    articles = [
        Article(title="Edu", source="e.com", url="https://e.com/1",
                published_at=datetime.utcnow(), content="x", topics=["education"]),
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
        Article(title="Edu", source="e.com", url="https://e.com/1",
                published_at=datetime.utcnow(), content="x", topics=["education"]),
    ]
    assert notifier.notify_digest(articles) is True


# --- _send_webhook ---

def test_send_webhook_returns_true_on_200(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 200
    mocker.patch("app.src.slack_notifier.requests.post", return_value=mock_resp)

    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {"payload": "test"}) is True


def test_send_webhook_returns_false_on_non_200(mocker):
    mock_resp = mocker.MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "Bad Request"
    mocker.patch("app.src.slack_notifier.requests.post", return_value=mock_resp)

    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {"payload": "test"}) is False


def test_send_webhook_returns_false_on_request_exception(mocker):
    mocker.patch(
        "app.src.slack_notifier.requests.post",
        side_effect=requests.RequestException("timeout"),
    )

    assert SlackNotifier._send_webhook("https://hooks.slack.com/x", {"payload": "test"}) is False
