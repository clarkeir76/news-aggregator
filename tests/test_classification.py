"""Tests for topic classification"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from app.src.models import Article
from app.src.classification import KeywordClassifier, LLMClassifier


def make_article(title, content="", url="https://example.com/article"):
    return Article(
        title=title,
        source="example.com",
        url=url,
        published_at=datetime.utcnow(),
        content=content,
    )


# --- KeywordClassifier ---


@pytest.fixture
def classifier():
    return KeywordClassifier()


def test_classify_ai_article(classifier):
    article = make_article(
        "New GPT Model Released", "OpenAI released a new large language model"
    )
    assert "ai" in classifier.classify(article)


def test_classify_security_article(classifier):
    article = make_article(
        "Major Security Breach", "A new vulnerability was discovered affecting millions"
    )
    assert "cyber_security" in classifier.classify(article)


def test_classify_education_article(classifier):
    article = make_article(
        "New Online Learning Platform", "Universities adopt new e-learning for students"
    )
    assert "education" in classifier.classify(article)


def test_classify_always_runs_regardless_of_preset_topics(classifier):
    article = make_article(
        "Major Security Breach Exposes Millions",
        "A critical vulnerability allowed hackers to breach encrypted systems",
    )
    article.topics = ["tech"]
    assert "cyber_security" in classifier.classify(article)


def test_classify_default_to_tech(classifier):
    article = make_article(
        "Random Article", "This article has no clear topic keywords at all"
    )
    assert "tech" in classifier.classify(article)


def test_keyword_classify_and_filter_keeps_all_articles(classifier):
    """KeywordClassifier never discards — no confidence in rejection."""
    articles = [
        make_article("Sport scores today"),
        make_article("New AI model released"),
    ]
    result = classifier.classify_and_filter(articles)
    assert len(result) == 2


# --- LLMClassifier ---


@pytest.fixture
def mock_openai(mocker):
    client = MagicMock()
    mocker.patch("app.src.classification.openai.OpenAI", return_value=client)
    return client


def test_llm_classifier_assigns_topics(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps(
        {
            "1": ["tech"],
            "2": ["ai", "tech"],
        }
    )

    articles = [
        make_article("New iPhone Released", url="https://example.com/1"),
        make_article("OpenAI releases GPT-5", url="https://example.com/2"),
    ]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.classify_and_filter(articles)

    assert len(result) == 2
    assert result[0].topics == ["tech"]
    assert result[1].topics == ["ai", "tech"]


def test_llm_classifier_discards_unmatched_articles(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps(
        {
            "1": ["tech"],
            "2": [],
        }
    )

    articles = [
        make_article("New developer tool", url="https://example.com/1"),
        make_article("Local football results", url="https://example.com/2"),
    ]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.classify_and_filter(articles)

    assert len(result) == 1
    assert result[0].url == "https://example.com/1"


def test_llm_classifier_strips_invalid_topics(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps(
        {
            "1": ["tech", "sports", "finance"],
        }
    )

    articles = [make_article("Tech and sports news", url="https://example.com/1")]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.classify_and_filter(articles)

    assert result[0].topics == ["tech"]


def test_llm_classifier_falls_back_to_keywords_on_failure(mock_openai):
    mock_openai.chat.completions.create.side_effect = Exception("API error")

    articles = [
        make_article(
            "New vulnerability discovered",
            "Hackers exploited a security breach in major software",
            url="https://example.com/1",
        )
    ]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.classify_and_filter(articles)

    assert len(result) == 1
    assert "cyber_security" in result[0].topics


def test_topic_descriptions_contain_exclusion_criteria():
    """Topic descriptions must include explicit EXCLUDE guidance for tech and education."""
    from app.src.classification import TOPICS

    assert (
        "EXCLUDE" in TOPICS["tech"]
    ), "tech topic must have explicit exclusion criteria"
    assert (
        "EXCLUDE" in TOPICS["education"]
    ), "education topic must have explicit exclusion criteria"
    assert (
        "post-18" in TOPICS["education"].lower()
        or "post 18" in TOPICS["education"].lower()
    )
    assert "consumer" in TOPICS["tech"].lower()


def test_cluster_stories_merges_same_story(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1, 2], [3]]})

    articles = [
        make_article("GreyVibe hackers use AI", url="https://a.com/1"),
        make_article("Russia-linked GreyVibe uses ChatGPT", url="https://b.com/1"),
        make_article("Unrelated story", url="https://c.com/1"),
    ]
    # Give second article more content so it becomes primary
    articles[0].content = "short"
    articles[1].content = "much longer content about the same story"

    classifier = LLMClassifier(api_key="test-key")
    result = classifier.cluster_stories(articles)

    assert len(result) == 2
    primary = next(a for a in result if "GreyVibe" in a.title or "Russia" in a.title)
    assert len(primary.related_urls) == 1


def test_cluster_stories_skips_on_failure(mock_openai):
    mock_openai.chat.completions.create.side_effect = Exception("API error")

    articles = [
        make_article("Story A", url="https://a.com/1"),
        make_article("Story B", url="https://b.com/1"),
    ]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.cluster_stories(articles)

    assert len(result) == 2  # unchanged on failure


def test_cluster_stories_single_article_skips_llm(mock_openai):
    articles = [make_article("Only one", url="https://a.com/1")]
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.cluster_stories(articles)

    assert len(result) == 1
    mock_openai.chat.completions.create.assert_not_called()


def test_llm_classifier_handles_empty_input(mock_openai):
    classifier = LLMClassifier(api_key="test-key")
    result = classifier.classify_and_filter([])
    assert result == []
    mock_openai.chat.completions.create.assert_not_called()


def test_llm_classifier_chunks_large_batches(mock_openai):
    import json
    from app.src.classification import CLASSIFICATION_BATCH_SIZE

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"1": ["tech"]})

    articles = [
        make_article(f"Article {i}", url=f"https://example.com/{i}")
        for i in range(CLASSIFICATION_BATCH_SIZE + 1)
    ]
    classifier = LLMClassifier(api_key="test-key")
    classifier.classify_and_filter(articles)

    # Should have made 2 API calls for BATCH_SIZE+1 articles
    assert mock_openai.chat.completions.create.call_count == 2
