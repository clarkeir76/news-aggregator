"""
Persistence integration tests against DynamoDB Local.

These tests run against a real DynamoDB Local instance and catch issues
that mocked unit tests cannot — real scan behaviour, actual FilterExpression
evaluation, correct item serialisation/deserialisation round-trips.

Skipped automatically if DynamoDB Local is not running.
Start it with: docker-compose up -d dynamodb-local
"""

import os
import uuid
import pytest
import boto3
from datetime import datetime, timezone

DYNAMO_LOCAL_URL = "http://localhost:8000"
TEST_TABLE = f"test-articles-{uuid.uuid4().hex[:8]}"


def _local_client():
    return boto3.client(
        "dynamodb",
        endpoint_url=DYNAMO_LOCAL_URL,
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def _dynamo_local_available() -> bool:
    try:
        _local_client().list_tables()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def store():
    """Create a real DynamoDB Local table and return a DynamoDBStore against it."""
    if not _dynamo_local_available():
        pytest.skip(
            "DynamoDB Local not running — start with: docker-compose up -d dynamodb-local"
        )

    client = _local_client()
    client.create_table(
        TableName=TEST_TABLE,
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

    from app.src.persistence import DynamoDBStore

    s = DynamoDBStore(
        table_name=TEST_TABLE,
        region_name="us-east-1",
        endpoint_url=DYNAMO_LOCAL_URL,
    )
    yield s

    client.delete_table(TableName=TEST_TABLE)


@pytest.fixture
def article():
    from app.src.models import Article

    return Article(
        title=f"Test Article {uuid.uuid4().hex[:6]}",
        source="example.com",
        url=f"https://example.com/{uuid.uuid4().hex}",
        published_at=datetime.now(timezone.utc),
        content="Test content " * 20,
        topics=["tech"],
    )


# ── Round-trip tests ──────────────────────────────────────────────────────────


def test_save_and_retrieve_article(store, article):
    article_id = store.save_article(article)
    assert article_id is not None

    results = store.get_recent_articles(limit=100)
    urls = [a.url for a in results]
    assert article.url in urls


def test_get_recent_articles_returns_stored_article_objects(store, article):
    from app.src.models import StoredArticle

    store.save_article(article)
    results = store.get_recent_articles(limit=100)
    assert all(isinstance(r, StoredArticle) for r in results)


def test_gsi_keys_stored_but_not_in_returned_objects(store, article):
    """
    Regression: persistence.py writes url_gsi_pk etc. as DynamoDB GSI keys.
    They must not appear as attributes on StoredArticle objects.
    """
    store.save_article(article)
    results = store.get_recent_articles(limit=100)
    for result in results:
        assert not hasattr(result, "url_gsi_pk")
        assert not hasattr(result, "source_date_gsi_pk")


def test_system_config_record_not_returned_as_article(store):
    """
    Regression: save_last_run_time() writes a SYSTEM#config record.
    get_recent_articles() must not return it as a StoredArticle.
    """
    now = datetime.now(timezone.utc)
    store.save_last_run_time(now)

    results = store.get_recent_articles(limit=100)
    for result in results:
        assert result.url != "SYSTEM#config"
        assert hasattr(result, "title")


def test_last_run_time_round_trip(store):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    store.save_last_run_time(now)

    retrieved = store.get_last_run_time()
    assert retrieved is not None
    assert retrieved.replace(tzinfo=timezone.utc).replace(microsecond=0) == now.replace(
        microsecond=0
    )


def test_update_article_summary(store, article):
    article_id = store.save_article(article)
    assert store.update_article(article_id, {"last_summary": "A real summary."})

    results = store.get_recent_articles(limit=100)
    saved = next((a for a in results if a.url == article.url), None)
    assert saved is not None
    assert saved.last_summary == "A real summary."


def test_deduplication_sees_previously_saved_articles(store, article):
    """
    Regression: second run must see articles from first run for deduplication.
    This is the scenario that was broken by the url_gsi_pk crash.
    """
    from app.src.deduplication import Deduplicator
    from app.src.models import Article

    store.save_article(article)
    existing = store.get_recent_articles(limit=100)
    assert len(existing) >= 1

    # A duplicate article with the same URL
    duplicate = Article(
        title=article.title,
        source=article.source,
        url=article.url,
        published_at=article.published_at,
        content=article.content,
        topics=article.topics,
    )

    deduplicator = Deduplicator()
    unique, stats = deduplicator.deduplicate([duplicate], existing)

    assert len(unique) == 0
    assert stats["url_duplicates"] == 1
