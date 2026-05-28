"""Tests for article content extraction"""

import pytest
from app.src.content_extractor import ContentExtractor, MIN_CONTENT_LENGTH


@pytest.fixture
def extractor():
    return ContentExtractor()


def test_uses_rss_content_when_long_enough(extractor):
    rss_content = "A" * MIN_CONTENT_LENGTH
    result = extractor.get_content("https://example.com/article", rss_content)
    assert result == rss_content


def test_fetches_article_when_rss_too_short(mocker, extractor):
    mocker.patch(
        "app.src.content_extractor.trafilatura.fetch_url",
        return_value="<html>article</html>",
    )
    mocker.patch(
        "app.src.content_extractor.trafilatura.extract",
        return_value="Full article text from page",
    )

    result = extractor.get_content("https://example.com/article", "Short")

    assert result == "Full article text from page"


def test_falls_back_to_rss_when_fetch_returns_nothing(mocker, extractor):
    mocker.patch("app.src.content_extractor.trafilatura.fetch_url", return_value=None)

    result = extractor.get_content("https://example.com/article", "Short RSS")

    assert result == "Short RSS"


def test_falls_back_to_rss_when_extraction_returns_nothing(mocker, extractor):
    mocker.patch(
        "app.src.content_extractor.trafilatura.fetch_url", return_value="<html></html>"
    )
    mocker.patch("app.src.content_extractor.trafilatura.extract", return_value=None)

    result = extractor.get_content("https://example.com/article", "Short RSS")

    assert result == "Short RSS"


def test_falls_back_to_rss_on_network_exception(mocker, extractor):
    mocker.patch(
        "app.src.content_extractor.trafilatura.fetch_url",
        side_effect=Exception("connection refused"),
    )

    result = extractor.get_content("https://example.com/article", "Short RSS")

    assert result == "Short RSS"


def test_does_not_fetch_when_content_meets_threshold(mocker, extractor):
    mock_fetch = mocker.patch("app.src.content_extractor.trafilatura.fetch_url")

    extractor.get_content("https://example.com/article", "A" * MIN_CONTENT_LENGTH)

    mock_fetch.assert_not_called()
