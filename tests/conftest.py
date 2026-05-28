"""Fixtures for testing"""

import pytest
from datetime import datetime
from app.src.models import Article


@pytest.fixture
def sample_article():
    """Sample article for testing"""
    return Article(
        title="Sample Article",
        source="example.com",
        url="https://example.com/article",
        published_at=datetime.utcnow(),
        content="This is sample content for testing purposes.",
        topics=["tech"],
    )


@pytest.fixture
def sample_articles():
    """Multiple sample articles"""
    return [
        Article(
            title="Article 1",
            source="source1.com",
            url="https://source1.com/article1",
            published_at=datetime.utcnow(),
            content="Content 1",
            topics=["tech"],
        ),
        Article(
            title="Article 2",
            source="source2.com",
            url="https://source2.com/article2",
            published_at=datetime.utcnow(),
            content="Content 2",
            topics=["ai"],
        ),
        Article(
            title="Article 3",
            source="source3.com",
            url="https://source3.com/article3",
            published_at=datetime.utcnow(),
            content="Content 3",
            topics=["cyber_security"],
        ),
    ]
