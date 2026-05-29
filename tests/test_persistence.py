"""Tests for DynamoDB persistence layer."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from botocore.exceptions import ClientError

from app.src.models import Article, StoredArticle
from app.src.persistence import DynamoDBStore


@pytest.fixture
def mock_table(mocker):
    """Mock DynamoDB table — returns a realistic item including GSI keys."""
    table = MagicMock()
    mocker.patch(
        "app.src.persistence.boto3.resource"
    ).return_value.Table.return_value = table
    return table


@pytest.fixture
def store(mock_table):
    return DynamoDBStore(table_name="test-table", region_name="eu-west-1")


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


def make_dynamo_item(article_id="abc-123"):
    """Realistic DynamoDB item including GSI keys that caused the bug."""
    return {
        "pk": f"ARTICLE#{article_id}",
        "sk": "METADATA",
        "article_id": article_id,
        "title": "Test Article",
        "source": "example.com",
        "url": "https://example.com/article",
        "published_at": "2024-01-15T10:00:00",
        "fetched_at": "2024-01-15T10:00:00",
        "first_seen_at": "2024-01-15T10:00:00",
        "last_seen_at": "2024-01-15T10:00:00",
        "content": "Test content",
        "topics": ["tech"],
        "related_urls": [],
        "content_hash": "abc",
        "canonical_url": None,
        "last_summary": None,
        "update_count": 0,
        "is_new": True,
        # GSI keys stored by persistence.py — must not crash from_dict()
        "url_gsi_pk": "URL#https://example.com/article",
        "source_date_gsi_pk": "SOURCE#example.com",
        "source_date_gsi_sk": "DATE#2024-01-15T10:00:00",
    }


# --- save_article ---


def test_save_article_returns_uuid(store, mock_table, article):
    mock_table.put_item.return_value = {}
    article_id = store.save_article(article)
    assert article_id is not None
    assert len(article_id) == 36  # UUID format


def test_save_article_sets_gsi_keys(store, mock_table, article):
    mock_table.put_item.return_value = {}
    store.save_article(article)

    item = mock_table.put_item.call_args[1]["Item"]
    assert item["pk"].startswith("ARTICLE#")
    assert item["sk"] == "METADATA"
    assert item["url_gsi_pk"] == f"URL#{article.url}"
    assert item["source_date_gsi_pk"] == f"SOURCE#{article.source}"


def test_save_article_returns_none_on_error(store, mock_table, article):
    mock_table.put_item.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "error"}}, "put_item"
    )
    assert store.save_article(article) is None


# --- get_recent_articles ---


def test_get_recent_articles_returns_stored_articles(store, mock_table):
    mock_table.scan.return_value = {"Items": [make_dynamo_item()]}
    results = store.get_recent_articles(limit=10)

    assert len(results) == 1
    assert isinstance(results[0], StoredArticle)
    assert results[0].title == "Test Article"


def test_get_recent_articles_handles_gsi_keys_without_crashing(store, mock_table):
    """Regression test: DynamoDB items contain GSI keys not in StoredArticle."""
    item = make_dynamo_item()
    assert "url_gsi_pk" in item  # confirm the test item has the problematic keys

    mock_table.scan.return_value = {"Items": [item]}
    results = store.get_recent_articles()  # must not raise

    assert len(results) == 1
    assert results[0].url == "https://example.com/article"


def test_get_recent_articles_returns_empty_on_error(store, mock_table):
    mock_table.scan.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "error"}}, "scan"
    )
    assert store.get_recent_articles() == []


# --- update_article ---


def test_update_article_returns_true_on_success(store, mock_table):
    mock_table.update_item.return_value = {}
    assert store.update_article("abc-123", {"last_summary": "A summary"}) is True


def test_update_article_returns_false_on_error(store, mock_table):
    mock_table.update_item.side_effect = ClientError(
        {"Error": {"Code": "500", "Message": "error"}}, "update_item"
    )
    assert store.update_article("abc-123", {"last_summary": "A summary"}) is False


# --- last_run_time ---


def test_get_last_run_time_returns_none_when_missing(store, mock_table):
    mock_table.get_item.return_value = {}
    assert store.get_last_run_time() is None


def test_get_last_run_time_returns_datetime(store, mock_table):
    mock_table.get_item.return_value = {
        "Item": {
            "pk": "SYSTEM#config",
            "sk": "last_run",
            "timestamp": "2024-01-15T10:00:00",
        }
    }
    result = store.get_last_run_time()
    assert isinstance(result, datetime)
    assert result.year == 2024


def test_save_last_run_time_calls_put_item(store, mock_table):
    now = datetime.now(timezone.utc)
    store.save_last_run_time(now)

    item = mock_table.put_item.call_args[1]["Item"]
    assert item["pk"] == "SYSTEM#config"
    assert item["sk"] == "last_run"
    assert now.isoformat() in item["timestamp"]
