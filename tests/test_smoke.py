"""
Smoke tests — no mocking. These instantiate real library clients to catch
version incompatibilities (e.g. openai vs httpx) that unit tests miss entirely.
"""


def test_openai_client_initializes():
    """openai.OpenAI() must construct without error against the installed httpx."""
    import openai
    client = openai.OpenAI(api_key="test-key")
    assert client is not None


def test_summarizer_initializes():
    """Summarizer must be able to build a real openai client."""
    from app.src.summarization import Summarizer
    s = Summarizer(api_key="test-key")
    assert s.client is not None


def test_trafilatura_imports():
    """trafilatura and its lxml dependency must be compatible."""
    import trafilatura
    assert callable(trafilatura.fetch_url)
    assert callable(trafilatura.extract)


def test_content_extractor_initializes():
    from app.src.content_extractor import ContentExtractor
    assert ContentExtractor() is not None


def test_keyword_classifier_initializes():
    from app.src.classification import KeywordClassifier
    c = KeywordClassifier()
    assert callable(c.classify)
    assert callable(c.classify_and_filter)


def test_llm_classifier_initializes():
    """LLMClassifier must construct a real openai client without error."""
    from app.src.classification import LLMClassifier
    c = LLMClassifier(api_key="test-key")
    assert c.client is not None
    assert callable(c.classify_and_filter)


def test_feedparser_parse_accepts_no_timeout_kwarg():
    """feedparser.parse() does not accept a timeout kwarg in v6 — must use socket."""
    import feedparser
    import inspect
    sig = inspect.signature(feedparser.parse)
    assert "timeout" not in sig.parameters, (
        "feedparser.parse() gained a timeout param — remove the socket workaround in ingestion.py"
    )


def test_feedparser_parse_called_without_timeout():
    """RSSIngester must be able to call feedparser.parse() without raising TypeError."""
    import feedparser
    from unittest.mock import patch, MagicMock
    mock_feed = MagicMock()
    mock_feed.bozo = False
    mock_feed.entries = []
    with patch("feedparser.parse", return_value=mock_feed) as mock_parse:
        from app.src.ingestion import RSSIngester
        ingester = RSSIngester()
        ingester.ingest_feed("https://example.com/rss")
        # Verify parse was called with only the URL, no timeout kwarg
        call_kwargs = mock_parse.call_args.kwargs if mock_parse.call_args else {}
        assert "timeout" not in call_kwargs


def test_boto3_resource_initializes():
    """boto3 DynamoDB resource must construct (no connection made until first request)."""
    import boto3
    resource = boto3.resource("dynamodb", region_name="us-east-1")
    assert resource is not None


def test_rapidfuzz_imports():
    from rapidfuzz import fuzz
    assert callable(fuzz.ratio)


def test_requests_imports():
    import requests
    assert callable(requests.post)


def test_all_app_modules_importable():
    """Every app module must be importable — catches missing __init__ or bad syntax."""
    from app.src import (  # noqa: F401
        config,
        models,
        ingestion,
        content_extractor,
        classification,
        deduplication,
        persistence,
        summarization,
        slack_notifier,
        orchestrator,
    )
