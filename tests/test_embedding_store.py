"""Tests for the Qdrant embedding store."""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.src.models import Article


@pytest.fixture
def article():
    return Article(
        title="OpenAI releases GPT-5",
        source="techcrunch.com",
        url="https://techcrunch.com/gpt5",
        published_at=datetime.now(timezone.utc),
        content="OpenAI has released GPT-5.",
        topics=["ai", "tech"],
    )


@pytest.fixture
def mock_qdrant(mocker):
    client = MagicMock()
    client.get_collections.return_value.collections = []
    mocker.patch("app.src.embedding_store.QdrantClient", return_value=client)
    return client


@pytest.fixture
def mock_openai(mocker):
    client = MagicMock()
    client.embeddings.create.return_value.data = [MagicMock(embedding=[0.1] * 1536)]
    mocker.patch("app.src.embedding_store.openai.OpenAI", return_value=client)
    return client


@pytest.fixture
def store(mock_qdrant, mock_openai):
    from app.src.embedding_store import EmbeddingStore

    return EmbeddingStore(
        qdrant_url="http://localhost:6333",
        openai_api_key="test-key",
    )


# --- Initialisation ---


def test_creates_collection_if_missing(mock_qdrant, mock_openai):
    from app.src.embedding_store import EmbeddingStore, COLLECTION_NAME

    EmbeddingStore(qdrant_url="http://localhost:6333", openai_api_key="test-key")
    mock_qdrant.create_collection.assert_called_once()
    call_kwargs = mock_qdrant.create_collection.call_args.kwargs
    assert call_kwargs["collection_name"] == COLLECTION_NAME


def test_skips_collection_creation_if_exists(mock_qdrant, mock_openai):
    from app.src.embedding_store import EmbeddingStore, COLLECTION_NAME

    existing = MagicMock()
    existing.name = COLLECTION_NAME
    mock_qdrant.get_collections.return_value.collections = [existing]

    EmbeddingStore(qdrant_url="http://localhost:6333", openai_api_key="test-key")
    mock_qdrant.create_collection.assert_not_called()


# --- store() ---


def test_store_embeds_title_and_summary(store, mock_openai, article):
    store.store(article, summary="GPT-5 is the latest model from OpenAI.")

    call_input = mock_openai.embeddings.create.call_args.kwargs["input"]
    assert "OpenAI releases GPT-5" in call_input
    assert "GPT-5 is the latest model" in call_input


def test_store_embeds_title_only_when_no_summary(store, mock_openai, article):
    store.store(article, summary="")

    call_input = mock_openai.embeddings.create.call_args.kwargs["input"]
    assert call_input == article.title


def test_store_upserts_to_qdrant(store, mock_qdrant, article):
    store.store(article, summary="A summary.")

    mock_qdrant.upsert.assert_called_once()
    point = mock_qdrant.upsert.call_args.kwargs["points"][0]
    assert point.payload["url"] == article.url
    assert point.payload["title"] == article.title
    assert "ai" in point.payload["topics"]


def test_store_returns_false_on_error(store, mock_qdrant, article):
    mock_qdrant.upsert.side_effect = Exception("connection refused")
    result = store.store(article)
    assert result is False


def test_store_uses_deterministic_id(store, mock_qdrant, article):
    store.store(article)
    store.store(article)  # same article
    # Both upserts should use the same point ID (URL-based UUID5)
    ids = [call.kwargs["points"][0].id for call in mock_qdrant.upsert.call_args_list]
    assert ids[0] == ids[1]


# --- search() ---


def test_search_returns_results(store, mock_qdrant, mock_openai):
    mock_result = MagicMock()
    mock_result.score = 0.92
    mock_result.payload = {
        "title": "GPT-5 released",
        "url": "https://example.com",
        "topics": ["ai"],
        "source": "example.com",
        "published_at": "2026-06-01T08:00:00",
        "summary": "OpenAI released GPT-5.",
    }
    mock_qdrant.search.return_value = [mock_result]

    results = store.search("latest OpenAI models", limit=5)

    assert len(results) == 1
    assert results[0]["score"] == 0.92
    assert results[0]["title"] == "GPT-5 released"


def test_search_with_topic_filter(store, mock_qdrant, mock_openai):
    mock_qdrant.search.return_value = []
    store.search("AI news", topic="ai")

    call_kwargs = mock_qdrant.search.call_args.kwargs
    assert call_kwargs["query_filter"] is not None


def test_search_returns_empty_on_error(store, mock_qdrant, mock_openai):
    mock_qdrant.search.side_effect = Exception("search failed")
    results = store.search("test query")
    assert results == []
