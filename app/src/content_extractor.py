"""Article content extraction — fetches full text when RSS content is insufficient."""

import logging
from typing import Optional
import trafilatura

logger = logging.getLogger(__name__)

MIN_CONTENT_LENGTH = 200  # chars below which we attempt to fetch the full article


class ContentExtractor:
    """
    Extracts article text, falling back to fetching the full page when the RSS
    entry provides insufficient content.

    trafilatura handles the HTTP fetch and extraction. To add special handling
    for a specific domain, subclass and override _fetch_and_extract.
    """

    def __init__(self, fetch_timeout: int = 15):
        self.fetch_timeout = fetch_timeout

    def get_content(self, url: str, rss_content: str) -> str:
        """
        Return the best available content for an article.

        Uses RSS content if it meets the minimum length threshold; otherwise
        attempts to fetch and extract text from the article URL.
        """
        if len(rss_content.strip()) >= MIN_CONTENT_LENGTH:
            return rss_content

        logger.debug(f"RSS content too short ({len(rss_content)} chars), fetching: {url}")
        fetched = self._fetch_and_extract(url)

        if fetched:
            logger.debug(f"Fetched {len(fetched)} chars from {url}")
            return fetched

        logger.warning(f"Could not fetch article content, using RSS summary: {url}")
        return rss_content

    def _fetch_and_extract(self, url: str) -> Optional[str]:
        """Fetch a URL and extract its main article text."""
        try:
            html = trafilatura.fetch_url(url)
            if not html:
                logger.warning(f"Empty response fetching article: {url}")
                return None

            text = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )

            if not text:
                logger.warning(f"trafilatura could not extract text from: {url}")
                return None

            return text

        except Exception as e:
            logger.warning(f"Failed to fetch/extract article {url}: {e}")
            return None
