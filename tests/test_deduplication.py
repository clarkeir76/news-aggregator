"""Tests for deduplication logic"""

import pytest
from datetime import datetime
from app.src.models import Article
from app.src.deduplication import Deduplicator


@pytest.fixture
def deduplicator():
    return Deduplicator()


def test_deduplicate_exact_url_match(deduplicator):
    """Test exact URL deduplication"""
    article1 = Article(
        title="Article",
        source="techcrunch.com",
        url="https://techcrunch.com/article",
        published_at=datetime.utcnow(),
        content="Content 1",
    )

    article2 = Article(
        title="Article",
        source="techcrunch.com",
        url="https://techcrunch.com/article",
        published_at=datetime.utcnow(),
        content="Content 2",
    )

    unique, stats = deduplicator.deduplicate([article1, article2])
    assert len(unique) == 1
    assert stats["url_duplicates"] == 1


def test_deduplicate_content_hash_match(deduplicator):
    """Test content hash deduplication"""
    content = "Same content"
    article1 = Article(
        title="Article 1",
        source="source1.com",
        url="https://source1.com/article",
        published_at=datetime.utcnow(),
        content=content,
    )

    article2 = Article(
        title="Article 2",
        source="source2.com",
        url="https://source2.com/article",
        published_at=datetime.utcnow(),
        content=content,
    )

    unique, stats = deduplicator.deduplicate([article1, article2])
    assert len(unique) == 1
    assert stats["content_hash_duplicates"] == 1


def test_deduplicate_fuzzy_title_match(deduplicator):
    """Test fuzzy title deduplication"""
    article1 = Article(
        title="New AI Model Released",
        source="openai.com",
        url="https://openai.com/article1",
        published_at=datetime.utcnow(),
        content="Content about new AI model",
    )

    article2 = Article(
        title="OpenAI Releases New AI Model",
        source="openai.com",
        url="https://openai.com/article2",
        published_at=datetime.utcnow(),
        content="Different content about new AI model",
    )

    unique, stats = deduplicator.deduplicate([article1, article2])
    assert len(unique) == 1
    assert stats["title_fuzzy_duplicates"] == 1


def test_deduplicate_different_sources_no_match(deduplicator):
    """Test that similar titles from different sources are not deduplicated"""
    article1 = Article(
        title="New AI Model Released",
        source="openai.com",
        url="https://openai.com/article1",
        published_at=datetime.utcnow(),
        content="OpenAI content",
    )

    article2 = Article(
        title="New AI Model Released",
        source="google.com",
        url="https://google.com/article2",
        published_at=datetime.utcnow(),
        content="Google content",
    )

    unique, stats = deduplicator.deduplicate([article1, article2])
    assert len(unique) == 2
    assert stats["title_fuzzy_duplicates"] == 0


def test_deduplicate_against_existing_articles(deduplicator):
    """Test deduplication against existing articles in storage"""
    existing = Article(
        title="Existing Article",
        source="techcrunch.com",
        url="https://techcrunch.com/existing",
        published_at=datetime.utcnow(),
        content="Existing content",
    )

    new = Article(
        title="Existing Article",
        source="techcrunch.com",
        url="https://techcrunch.com/existing",
        published_at=datetime.utcnow(),
        content="New content",
    )

    unique, stats = deduplicator.deduplicate([new], existing_articles=[existing])
    assert len(unique) == 0
    assert stats["url_duplicates"] == 1
