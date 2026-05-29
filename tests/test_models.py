"""Tests for data models"""

from datetime import datetime
from app.src.models import Article, StoredArticle, Topic


def test_article_creation():
    """Test creating an article"""
    article = Article(
        title="Test Article",
        source="techcrunch.com",
        url="https://techcrunch.com/article",
        published_at=datetime.utcnow(),
        content="Test content",
        topics=["tech"],
    )

    assert article.title == "Test Article"
    assert article.source == "techcrunch.com"
    assert article.content_hash is not None


def test_article_content_hash():
    """Test that content hash is computed"""
    content = "This is test content"
    article = Article(
        title="Test",
        source="test.com",
        url="https://test.com",
        published_at=datetime.utcnow(),
        content=content,
    )

    # Same content should produce same hash
    article2 = Article(
        title="Test 2",
        source="test.com",
        url="https://test2.com",
        published_at=datetime.utcnow(),
        content=content,
    )

    assert article.content_hash == article2.content_hash


def test_stored_article_from_article():
    """Test creating StoredArticle from Article"""
    article = Article(
        title="Test",
        source="test.com",
        url="https://test.com",
        published_at=datetime.utcnow(),
        content="Test content",
        topics=["tech"],
    )

    stored = StoredArticle.from_article(article, article_id="test-id")
    assert stored.article_id == "test-id"
    assert stored.is_new is True
    assert stored.update_count == 0


def test_article_to_dict_iso_format():
    """Test article serialization with ISO format dates"""
    article = Article(
        title="Test",
        source="test.com",
        url="https://test.com",
        published_at=datetime(2024, 1, 15, 10, 30, 45),
        content="Test content",
    )

    data = article.to_dict()
    assert data["published_at"] == "2024-01-15T10:30:45"
    assert isinstance(data["fetched_at"], str)  # utcnow() — just verify it serialised


def test_stored_article_from_dict_strips_dynamodb_gsi_keys():
    """DynamoDB items contain GSI keys not in the dataclass — must be stripped."""
    from app.src.models import StoredArticle

    data = {
        "title": "Test",
        "source": "test.com",
        "url": "https://test.com",
        "published_at": "2024-01-15T10:00:00",
        "fetched_at": "2024-01-15T10:00:00",
        "first_seen_at": "2024-01-15T10:00:00",
        "last_seen_at": "2024-01-15T10:00:00",
        "content": "Test content",
        "topics": ["tech"],
        "related_urls": [],
        "pk": "ARTICLE#abc",
        "sk": "METADATA",
        "url_gsi_pk": "URL#https://test.com",
        "source_date_gsi_pk": "SOURCE#test.com",
        "source_date_gsi_sk": "DATE#2024-01-15",
    }
    article = StoredArticle.from_dict(data)
    assert article.title == "Test"
    assert article.url == "https://test.com"


def test_topic_enum():
    """Test topic enumeration"""
    assert Topic.TECH.value == "tech"
    assert Topic.AI.value == "ai"
    assert Topic.CYBER_SECURITY.value == "cyber_security"
    assert Topic.EDUCATION.value == "education"

    topics = Topic.all_topics()
    assert len(topics) == 4
    assert "tech" in topics
