"""Tests for topic classification"""

import pytest
from datetime import datetime
from app.src.models import Article
from app.src.classification import KeywordClassifier


@pytest.fixture
def classifier():
    return KeywordClassifier()


def test_classify_ai_article(classifier):
    """Test classification of AI article"""
    article = Article(
        title="New GPT Model Released",
        source="openai.com",
        url="https://openai.com/gpt",
        published_at=datetime.utcnow(),
        content="OpenAI released a new large language model with improved capabilities",
    )

    topics = classifier.classify(article)
    assert "ai" in topics


def test_classify_security_article(classifier):
    """Test classification of security article"""
    article = Article(
        title="Major Security Breach",
        source="bleepingcomputer.com",
        url="https://bleepingcomputer.com/breach",
        published_at=datetime.utcnow(),
        content="A new vulnerability was discovered in popular software affecting millions",
    )

    topics = classifier.classify(article)
    assert "cyber_security" in topics


def test_classify_education_article(classifier):
    """Test classification of education article"""
    article = Article(
        title="New Online Learning Platform",
        source="edsurge.com",
        url="https://edsurge.com/platform",
        published_at=datetime.utcnow(),
        content="Universities adopt new e-learning platform for students",
    )

    topics = classifier.classify(article)
    assert "education" in topics


def test_classify_always_runs_regardless_of_preset_topics(classifier):
    """Classification always runs on content — pre-set topics are ignored"""
    article = Article(
        title="Major Security Breach Exposes Millions",
        source="example.com",
        url="https://example.com",
        published_at=datetime.utcnow(),
        content="A critical vulnerability allowed hackers to breach encrypted systems",
        topics=["tech"],  # pre-set topic that doesn't match content
    )

    topics = classifier.classify(article)
    assert "cyber_security" in topics


def test_classify_default_to_tech(classifier):
    """Test that unclassified articles default to tech"""
    article = Article(
        title="Random Article",
        source="example.com",
        url="https://example.com",
        published_at=datetime.utcnow(),
        content="This article has no clear topic",
    )

    topics = classifier.classify(article)
    assert "tech" in topics
