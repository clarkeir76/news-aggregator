"""Deduplication module"""

import logging
from typing import List, Set, Tuple
from rapidfuzz import fuzz
from urllib.parse import urlparse

from .models import Article

logger = logging.getLogger(__name__)


class Deduplicator:
    """Article deduplication"""

    def __init__(self, title_similarity_threshold: float = 0.85):
        self.title_similarity_threshold = title_similarity_threshold

    def deduplicate(
        self, articles: List[Article], existing_articles: List[Article] = None
    ) -> Tuple[List[Article], dict]:
        """
        Deduplicate articles using exact and fuzzy matching.

        Returns:
            Tuple of (unique_articles, stats)
        """
        if existing_articles is None:
            existing_articles = []

        stats = {
            "total_input": len(articles),
            "url_duplicates": 0,
            "content_hash_duplicates": 0,
            "title_fuzzy_duplicates": 0,
            "unique_output": 0,
        }

        # Build lookup sets from existing articles
        existing_urls = set()
        existing_content_hashes = set()
        existing_title_sources = []

        for article in existing_articles:
            existing_urls.add(article.url)
            if article.content_hash:
                existing_content_hashes.add(article.content_hash)
            existing_title_sources.append((article.title, article.source))

        # Deduplicate input articles among themselves
        unique_articles = []
        seen_urls = set()
        seen_content_hashes = set()
        seen_title_sources = []

        for article in articles:
            # Exact URL match
            if article.url in existing_urls or article.url in seen_urls:
                stats["url_duplicates"] += 1
                logger.debug(f"Duplicate URL: {article.url}")
                continue

            # Content hash match
            if (
                article.content_hash
                and (
                    article.content_hash in existing_content_hashes
                    or article.content_hash in seen_content_hashes
                )
            ):
                stats["content_hash_duplicates"] += 1
                logger.debug(f"Duplicate content hash: {article.content_hash[:8]}")
                continue

            # Fuzzy title + source match
            if self._is_fuzzy_duplicate(
                article.title, article.source, existing_title_sources + seen_title_sources
            ):
                stats["title_fuzzy_duplicates"] += 1
                logger.debug(f"Fuzzy duplicate: {article.title}")
                continue

            unique_articles.append(article)
            seen_urls.add(article.url)
            if article.content_hash:
                seen_content_hashes.add(article.content_hash)
            seen_title_sources.append((article.title, article.source))

        stats["unique_output"] = len(unique_articles)
        logger.info(
            f"Deduplication: {stats['total_input']} → {stats['unique_output']} "
            f"({stats['url_duplicates']} URL, {stats['content_hash_duplicates']} hash, "
            f"{stats['title_fuzzy_duplicates']} fuzzy)"
        )

        return unique_articles, stats

    def _is_fuzzy_duplicate(
        self, title: str, source: str, existing_title_sources: List[Tuple[str, str]]
    ) -> bool:
        """Check if article is a fuzzy duplicate using title similarity"""
        for existing_title, existing_source in existing_title_sources:
            # Only compare articles from similar sources
            if self._is_same_source(source, existing_source):
                similarity = fuzz.ratio(title.lower(), existing_title.lower())
                if similarity >= self.title_similarity_threshold:
                    return True

        return False

    @staticmethod
    def _is_same_source(source1: str, source2: str) -> bool:
        """Check if two sources are equivalent"""
        # Extract domain without www
        def normalize_source(s: str) -> str:
            s = s.replace("www.", "").split(".")[0].lower()
            return s

        return normalize_source(source1) == normalize_source(source2)
