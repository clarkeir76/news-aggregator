"""Main orchestration module"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List, Optional

from .models import Article
from .ingestion import RSSIngester, FeedConfig
from .classification import LLMClassifier, KeywordClassifier
from .content_extractor import ContentExtractor
from .deduplication import Deduplicator
from .persistence import DynamoDBStore
from .summarization import Summarizer
from .slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)


class NewsAggregator:
    """
    News aggregation pipeline.

      1. Ingest RSS feeds (title + RSS summary only — concurrent)
      2. Classify and filter (LLM batch — discard irrelevant articles)
      3. Fetch full article text (matched articles only — concurrent)
      4. Deduplicate against existing articles
      5. Persist to DynamoDB (optional)
      6. Summarise via OpenAI (concurrent)
      7. Post Slack digests
    """

    def __init__(
        self,
        feed_config_path: str,
        dynamodb_table: str = None,
        aws_region: str = "us-east-1",
        aws_endpoint_url: str = None,
        openai_api_key: str = None,
        slack_webhooks: dict = None,
        enable_summarization: bool = True,
        enable_slack: bool = True,
        slack_dry_run: bool = False,
        enable_persistence: bool = True,
        enable_llm_classification: bool = True,
        max_articles_per_feed: int = 50,
        max_concurrent_feeds: int = 10,
        max_concurrent_summarizations: int = 5,
        max_article_age_hours: int = 24,
    ):
        self.feed_config_path = feed_config_path
        self.max_concurrent_feeds = max_concurrent_feeds
        self.max_concurrent_summarizations = max_concurrent_summarizations

        self.ingester = RSSIngester(
            max_articles_per_feed=max_articles_per_feed,
            max_concurrent_feeds=max_concurrent_feeds,
            max_age_hours=max_article_age_hours,
        )

        self.classifier = (
            LLMClassifier(api_key=openai_api_key)
            if enable_llm_classification and openai_api_key
            else KeywordClassifier()
        )

        self.content_extractor = ContentExtractor()
        self.deduplicator = Deduplicator()

        self.store = None
        if enable_persistence and dynamodb_table:
            self.store = DynamoDBStore(
                table_name=dynamodb_table,
                region_name=aws_region,
                endpoint_url=aws_endpoint_url,
            )

        self.summarizer = None
        if enable_summarization and openai_api_key:
            self.summarizer = Summarizer(api_key=openai_api_key)

        self.notifier = None
        if enable_slack and slack_webhooks:
            self.notifier = SlackNotifier(webhook_urls=slack_webhooks, dry_run=slack_dry_run)

        self.stats = {
            "timestamp": "",
            "feeds_processed": 0,
            "articles_ingested": 0,
            "articles_classified": 0,
            "articles_deduplicated": 0,
            "articles_saved": 0,
            "articles_summarized": 0,
            "articles_notified": 0,
            "errors": [],
        }

    def run(self) -> dict:
        logger.info("Starting news aggregation pipeline")
        self.stats = {
            "timestamp": datetime.utcnow().isoformat(),
            "feeds_processed": 0,
            "articles_ingested": 0,
            "articles_classified": 0,
            "articles_deduplicated": 0,
            "articles_saved": 0,
            "articles_summarized": 0,
            "articles_notified": 0,
            "errors": [],
        }

        try:
            feed_configs = FeedConfig.load_from_yaml(self.feed_config_path)
            if not feed_configs:
                raise RuntimeError("No feeds loaded from configuration")
            self.stats["feeds_loaded"] = len(feed_configs)

            # Step 1: Ingest (title + RSS summary, concurrent)
            articles, ingest_stats = self.ingester.ingest_feeds(feed_configs)
            self.stats.update(ingest_stats)
            self.stats["articles_ingested"] = len(articles)
            logger.info(f"Ingested {len(articles)} articles from {len(feed_configs)} feeds")

            # Step 2: Classify and filter
            articles = self.classifier.classify_and_filter(articles)
            self.stats["articles_classified"] = len(articles)
            logger.info(f"{len(articles)} articles matched our topics")

            # Step 3: Fetch full article text (matched articles only, concurrent)
            articles = self._enrich_content(articles)

            # Step 4: Deduplicate
            existing_articles = self.store.get_recent_articles(limit=1000) if self.store else []
            logger.info(f"Retrieved {len(existing_articles)} existing articles for deduplication")
            unique_articles, dedup_stats = self.deduplicator.deduplicate(articles, existing_articles)
            self.stats.update(dedup_stats)

            # Step 5: Persist
            new_articles = []
            for article in unique_articles:
                if self.store:
                    article_id = self.store.save_article(article)
                    if article_id:
                        self.stats["articles_saved"] += 1
                        new_articles.append((article, article_id))
                else:
                    new_articles.append((article, None))

            # Step 6: Summarise (concurrent)
            summaries = self._summarise(new_articles)

            # Step 7: Notify
            if self.notifier and new_articles:
                articles_to_notify = [article for article, _ in new_articles]
                if self.notifier.notify_digest(articles_to_notify, summaries):
                    self.stats["articles_notified"] = len(articles_to_notify)

        except Exception as e:
            logger.error(f"Error in aggregation pipeline: {e}", exc_info=True)
            self.stats["errors"].append(str(e))

        logger.info(f"Pipeline completed. Stats: {self.stats}")
        return self.stats

    def _enrich_content(self, articles: List[Article]) -> List[Article]:
        """Fetch full article text concurrently for all matched articles."""
        if not articles:
            return []

        def fetch(article: Article) -> Article:
            article.content = self.content_extractor.get_content(article.url, article.content)
            return article

        enriched = []
        with ThreadPoolExecutor(max_workers=self.max_concurrent_feeds) as executor:
            futures = {executor.submit(fetch, article): article for article in articles}
            for future in as_completed(futures):
                try:
                    enriched.append(future.result())
                except Exception as e:
                    original = futures[future]
                    logger.warning(f"Content fetch failed for {original.url}: {e}")
                    enriched.append(original)

        logger.info(f"Enriched content for {len(enriched)} articles")
        return enriched

    def _summarise(self, new_articles: list) -> dict:
        """Summarise new articles concurrently. Returns dict of url -> summary."""
        if not self.summarizer or not new_articles:
            return {}

        def summarise_one(pair):
            article, article_id = pair
            summary = self.summarizer.summarize(article.content, article.title)
            if summary and self.store and article_id:
                self.store.update_article(article_id, {"last_summary": summary})
            return article.url, summary

        summaries = {}
        results = []
        with ThreadPoolExecutor(max_workers=self.max_concurrent_summarizations) as executor:
            futures = {executor.submit(summarise_one, pair): pair for pair in new_articles}
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    article, _ = futures[future]
                    logger.warning(f"Summarisation failed for {article.url}: {e}")

        for url, summary in results:
            if summary:
                summaries[url] = summary
                self.stats["articles_summarized"] += 1

        return summaries
