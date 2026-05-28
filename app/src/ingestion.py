"""RSS feed ingestion module"""

import logging
import feedparser
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import yaml

from .models import Article
from .content_extractor import ContentExtractor

logger = logging.getLogger(__name__)


class FeedConfig:
    """RSS feed configuration"""

    def __init__(self, url: str):
        self.url = url

    @classmethod
    def load_from_yaml(cls, config_path: str) -> List["FeedConfig"]:
        """Load feeds configuration from YAML file"""
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            return [cls(url=feed_item.get("url")) for feed_item in config.get("feeds", [])]
        except FileNotFoundError:
            logger.error(f"Feed config file not found: {config_path}")
            return []
        except yaml.YAMLError as e:
            logger.error(f"Error parsing feed config: {e}")
            return []


class RSSIngester:
    """RSS feed ingestion"""

    def __init__(self, max_articles_per_feed: int = 50, timeout: int = 10):
        self.max_articles_per_feed = max_articles_per_feed
        self.timeout = timeout
        self.extractor = ContentExtractor(fetch_timeout=timeout)

    def ingest_feed(self, feed_url: str) -> Tuple[List[Article], int]:
        """
        Ingest a single RSS feed.

        Returns:
            Tuple of (articles, error_count)
        """
        articles = []
        errors = 0

        logger.info(f"Ingesting feed: {feed_url}")

        try:
            feed = feedparser.parse(feed_url, timeout=self.timeout)

            if not feed.entries:
                logger.warning(f"No entries found in feed: {feed_url}")
                return [], 1

            if feed.bozo:
                logger.warning(f"Feed parse warning for {feed_url}: {feed.bozo_exception}")

            for i, entry in enumerate(feed.entries[: self.max_articles_per_feed]):
                try:
                    article = self._parse_entry(entry, feed_url)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error parsing entry {i} from {feed_url}: {e}")
                    errors += 1

        except Exception as e:
            logger.error(f"Failed to fetch feed {feed_url}: {e}")
            errors += 1

        logger.info(f"Ingested {len(articles)} articles from {feed_url} ({errors} errors)")
        return articles, errors

    def ingest_feeds(self, feed_configs: List[FeedConfig]) -> Tuple[List[Article], dict]:
        """
        Ingest multiple RSS feeds.

        Returns:
            Tuple of (articles, stats)
        """
        all_articles = []
        stats = {
            "total_feeds": len(feed_configs),
            "successful_feeds": 0,
            "failed_feeds": 0,
            "total_articles": 0,
            "total_errors": 0,
        }

        for feed_config in feed_configs:
            articles, errors = self.ingest_feed(feed_config.url)
            all_articles.extend(articles)
            stats["total_articles"] += len(articles)
            stats["total_errors"] += errors

            if errors > 0 or len(articles) == 0:
                stats["failed_feeds"] += 1
            else:
                stats["successful_feeds"] += 1

        return all_articles, stats

    def _parse_entry(self, entry: dict, feed_url: str) -> Optional[Article]:
        """Parse a single feed entry into an Article, fetching full text if needed."""
        try:
            title = entry.get("title", "").strip()
            if not title:
                return None

            url = entry.get("link", "").strip()
            if not url:
                return None

            published_at = self._parse_date(entry)

            rss_content = self._extract_rss_content(entry)
            content = self.extractor.get_content(url, rss_content)

            source = urlparse(feed_url).netloc

            return Article(
                title=title,
                source=source,
                url=url,
                published_at=published_at,
                content=content,
            )

        except Exception as e:
            logger.warning(f"Error parsing entry '{entry.get('title', '?')}': {e}")
            return None

    @staticmethod
    def _parse_date(entry: dict) -> datetime:
        """Extract published date from feed entry, falling back to now."""
        if entry.get("published_parsed"):
            try:
                return datetime(*entry.get("published_parsed")[:6])
            except Exception:
                pass
        if entry.get("updated_parsed"):
            try:
                return datetime(*entry.get("updated_parsed")[:6])
            except Exception:
                pass
        return datetime.utcnow()

    @staticmethod
    def _extract_rss_content(entry: dict) -> str:
        """Pull whatever text the RSS entry provides."""
        content_list = entry.get("content")
        if content_list:
            return content_list[0].value or ""
        return entry.get("summary") or ""
