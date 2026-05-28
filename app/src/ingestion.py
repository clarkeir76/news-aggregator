"""RSS feed ingestion module"""

import logging
import feedparser
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse
import yaml

from .models import Article

logger = logging.getLogger(__name__)


class FeedConfig:
    """RSS feed configuration"""

    def __init__(self, url: str, topics: List[str]):
        self.url = url
        self.topics = topics or []

    @classmethod
    def load_from_yaml(cls, config_path: str) -> List["FeedConfig"]:
        """Load feeds configuration from YAML file"""
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            feeds = []
            for feed_item in config.get("feeds", []):
                feeds.append(
                    cls(
                        url=feed_item.get("url"),
                        topics=feed_item.get("topics", []),
                    )
                )
            return feeds
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

    def ingest_feed(self, feed_url: str, topics: List[str]) -> Tuple[List[Article], int]:
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

            if feed.bozo:
                logger.warning(f"Feed parsing had issues: {feed.bozo_exception}")

            for i, entry in enumerate(feed.entries[: self.max_articles_per_feed]):
                try:
                    article = self._parse_entry(entry, feed_url, topics)
                    if article:
                        articles.append(article)
                except Exception as e:
                    logger.warning(f"Error parsing entry {i} from {feed_url}: {e}")
                    errors += 1

        except Exception as e:
            logger.error(f"Error ingesting feed {feed_url}: {e}")
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
            articles, errors = self.ingest_feed(feed_config.url, feed_config.topics)
            all_articles.extend(articles)
            stats["total_articles"] += len(articles)
            stats["total_errors"] += errors

            if errors > 0 or len(articles) == 0:
                stats["failed_feeds"] += 1
            else:
                stats["successful_feeds"] += 1

        return all_articles, stats

    @staticmethod
    def _parse_entry(entry: dict, feed_url: str, topics: List[str]) -> Optional[Article]:
        """Parse a single feed entry into Article"""
        try:
            title = entry.get("title", "").strip()
            if not title:
                return None

            url = entry.get("link", "").strip()
            if not url:
                return None

            # Get published date
            published_at = datetime.utcnow()
            if entry.get("published_parsed"):
                try:
                    from time import struct_time
                    from datetime import datetime as dt

                    published_at = dt(*entry.published_parsed[:6])
                except Exception as e:
                    logger.debug(f"Error parsing published date: {e}")

            # Get content
            content = ""
            if entry.get("summary"):
                content = entry.summary
            elif entry.get("content"):
                content = entry.content[0].value if entry.content else ""

            # Extract source from feed URL
            source = urlparse(feed_url).netloc

            return Article(
                title=title,
                source=source,
                url=url,
                published_at=published_at,
                content=content,
                topics=topics or [],
            )

        except Exception as e:
            logger.debug(f"Error parsing entry: {e}")
            return None
