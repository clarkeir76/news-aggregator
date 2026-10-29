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


def test_cluster_prompt_rules(mock_openai):
    """Clustering prompt must group same-event articles without an arbitrary cap."""
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1], [2]]})

    articles = [
        make_article("Story A", url="https://a.com/1"),
        make_article("Story B", url="https://b.com/1"),
    ]
    classifier = LLMClassifier(api_key="test-key")
    classifier.cluster_stories(articles)

    prompt = mock_openai.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    # Must instruct the LLM to group same-event articles
    assert "same specific event" in prompt.lower() or "exact" in prompt.lower()
    # Must explicitly handle different headline angles on the same event
    assert "angle" in prompt.lower() or "framing" in prompt.lower()
    # Must NOT impose an arbitrary per-group article cap
    assert "maximum of 3" not in prompt.lower()
    assert "max" not in prompt.lower() or "maximum" not in prompt.lower()


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


# --- ENABLED_TOPICS ---


def test_keyword_classifier_respects_enabled_topics():
    c = KeywordClassifier(enabled_topics=["ai"])
    article = make_article("Major Security Breach", "A new vulnerability was found")
    assert c.classify(article) == []


def test_keyword_classifier_drops_unmatched_when_tech_disabled():
    c = KeywordClassifier(enabled_topics=["ai"])
    articles = [
        make_article("Weather today", "Sunny", url="https://example.com/1"),
        make_article(
            "New LLM released", "A large language model", url="https://example.com/2"
        ),
    ]
    result = c.classify_and_filter(articles)
    assert [a.url for a in result] == ["https://example.com/2"]
    assert result[0].topics == ["ai"]


def test_keyword_classifier_defaults_to_tech_when_tech_enabled():
    c = KeywordClassifier(enabled_topics=["tech", "ai"])
    assert c.classify(make_article("Weather today", "Sunny")) == ["tech"]


def test_llm_classifier_prompt_only_lists_enabled_topics(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"1": ["ai"]})
    classifier = LLMClassifier(api_key="test-key", enabled_topics=["ai"])
    classifier.client = mock_openai

    classifier.classify_and_filter([make_article("New LLM")])

    prompt = mock_openai.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "- ai:" in prompt
    for disabled in ("- tech:", "- cyber_security:", "- education:"):
        assert disabled not in prompt


def test_llm_classifier_discards_articles_matching_only_disabled_topics(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"1": ["tech"], "2": ["ai", "tech"]})
    classifier = LLMClassifier(api_key="test-key", enabled_topics=["ai"])
    classifier.client = mock_openai

    articles = [
        make_article("Cloud update", url="https://example.com/1"),
        make_article("AI tooling", url="https://example.com/2"),
    ]
    result = classifier.classify_and_filter(articles)

    assert [a.url for a in result] == ["https://example.com/2"]
    assert result[0].topics == ["ai"]


# --- Significance scoring ---


def _classify_with_response(mock_openai, payload, **kwargs):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps(payload)
    classifier = LLMClassifier(api_key="test-key", enabled_topics=["ai"], **kwargs)
    classifier.client = mock_openai
    articles = [
        make_article("Major model release", url="https://example.com/1"),
        make_article("Minor feature tweak", url="https://example.com/2"),
    ]
    return classifier.classify_and_filter(articles)


def test_llm_classifier_drops_articles_below_min_significance(mock_openai):
    result = _classify_with_response(
        mock_openai,
        {
            "1": {"topics": ["ai"], "significance": 5},
            "2": {"topics": ["ai"], "significance": 3},
        },
    )
    assert [a.url for a in result] == ["https://example.com/1"]
    assert result[0].topics == ["ai"]


def test_llm_classifier_min_significance_is_configurable(mock_openai):
    result = _classify_with_response(
        mock_openai,
        {
            "1": {"topics": ["ai"], "significance": 5},
            "2": {"topics": ["ai"], "significance": 3},
        },
        min_significance=3,
    )
    assert len(result) == 2


def test_llm_classifier_default_threshold_keeps_score_of_four(mock_openai):
    result = _classify_with_response(
        mock_openai,
        {
            "1": {"topics": ["ai"], "significance": 4},
            "2": {"topics": [], "significance": 5},
        },
    )
    assert [a.url for a in result] == ["https://example.com/1"]


def test_llm_classifier_accepts_bare_topic_list_without_score(mock_openai):
    result = _classify_with_response(mock_openai, {"1": ["ai"], "2": []})
    assert [a.url for a in result] == ["https://example.com/1"]


def test_ai_topic_requires_ai_to_be_the_subject():
    from app.src.classification import TOPICS

    description = TOPICS["ai"]
    assert "primarily ABOUT AI" in description
    assert "student using AI for homework" in description


def test_llm_classifier_prompt_requests_significance_score(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"1": {"topics": ["ai"], "significance": 5}})
    classifier = LLMClassifier(api_key="test-key", enabled_topics=["ai"])
    classifier.client = mock_openai

    classifier.classify_and_filter([make_article("New LLM")])

    prompt = mock_openai.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "significance" in prompt


# --- Clustering improvements ---


def test_cluster_prompt_includes_summary_snippets_and_analysis_rule(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1], [2]]})
    articles = [
        make_article("Model launch", "Gemini 4 Carbon unveiled", "https://a.com/1"),
        make_article("Looks like a diamond", "Hands-on review", "https://b.com/1"),
    ]
    LLMClassifier(api_key="test-key").cluster_stories(articles)

    prompt = mock_openai.chat.completions.create.call_args.kwargs["messages"][1][
        "content"
    ]
    assert "Summary: Gemini 4 Carbon unveiled" in prompt
    assert "review" in prompt.lower() and "same group" in prompt.lower()


def test_cluster_uses_cluster_model_when_set(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1], [2]]})
    articles = [
        make_article("A", url="https://a.com/1"),
        make_article("B", url="https://b.com/1"),
    ]
    LLMClassifier(
        api_key="test-key", model="gpt-4o-mini", cluster_model="gpt-4.1"
    ).cluster_stories(articles)

    assert mock_openai.chat.completions.create.call_args.kwargs["model"] == "gpt-4.1"


def test_cluster_model_defaults_to_main_model(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1], [2]]})
    articles = [
        make_article("A", url="https://a.com/1"),
        make_article("B", url="https://b.com/1"),
    ]
    LLMClassifier(api_key="test-key", model="gpt-4o").cluster_stories(articles)

    assert mock_openai.chat.completions.create.call_args.kwargs["model"] == "gpt-4o"


def test_cluster_excludes_primary_url_from_related_urls(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1, 2, 3]]})
    articles = [
        make_article("Same story", "long content here", "https://a.com/1"),
        make_article("Same story", "x", "https://a.com/1"),
        make_article("Same story again", "y", "https://b.com/1"),
    ]
    result = LLMClassifier(api_key="test-key").cluster_stories(articles)

    assert len(result) == 1
    assert result[0].related_urls == ["https://b.com/1"]


def test_cluster_keeps_highest_significance(mock_openai):
    import json

    mock_openai.chat.completions.create.return_value.choices[
        0
    ].message.content = json.dumps({"groups": [[1, 2]]})
    articles = [
        make_article("Story", "longer content", "https://a.com/1"),
        make_article("Story", "x", "https://b.com/1"),
    ]
    articles[0].significance = 4
    articles[1].significance = 5
    result = LLMClassifier(api_key="test-key").cluster_stories(articles)

    assert result[0].significance == 5


def test_llm_classifier_sets_significance_on_articles(mock_openai):
    result = _classify_with_response(
        mock_openai,
        {
            "1": {"topics": ["ai"], "significance": 5},
            "2": {"topics": ["ai"], "significance": 4},
        },
    )
    assert [a.significance for a in result] == [5, 4]
