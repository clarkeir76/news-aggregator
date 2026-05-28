"""Main orchestration module"""

import logging
from typing import List, Optional
from datetime import datetime

from .models import Article
from .ingestion import RSSIngester, FeedConfig
from .classification import KeywordClassifier
from .deduplication import Deduplicator
from .persistence import DynamoDBStore
from .summarization import Summarizer
from .slack_notifier import SlackNotifier

logger = logging.getLogger(__name__)


class NewsAggregator:
    """Main news aggregation orchestrator"""

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
        max_articles_per_feed: int = 50,
    ):
        self.feed_config_path = feed_config_path

        self.ingester = RSSIngester(max_articles_per_feed=max_articles_per_feed)
        self.classifier = KeywordClassifier()
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

        self.stats = {}

    def run(self) -> dict:
        """
        Execute the full news aggregation pipeline.

        Returns:
            Dictionary with execution stats
        """
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
            # Step 1: Load feed configuration
            feed_configs = FeedConfig.load_from_yaml(self.feed_config_path)
            if not feed_configs:
                raise RuntimeError("No feeds loaded from configuration")

            self.stats["feeds_loaded"] = len(feed_configs)

            # Step 2: Ingest articles
            articles, ingest_stats = self.ingester.ingest_feeds(feed_configs)
            self.stats.update(ingest_stats)
            logger.info(f"Ingested {len(articles)} total articles")

            # Step 3: Classify articles
            articles = self.classifier.classify_articles(articles)
            self.stats["articles_classified"] = len(articles)

            # Step 4: Get existing articles for deduplication (skipped if no store)
            existing_articles = self.store.get_recent_articles(limit=1000) if self.store else []
            logger.info(f"Retrieved {len(existing_articles)} existing articles for deduplication")

            # Step 5: Deduplicate
            unique_articles, dedup_stats = self.deduplicator.deduplicate(
                articles, existing_articles
            )
            self.stats.update(dedup_stats)

            # Step 6: Store articles (skipped if no store)
            new_articles = []
            for article in unique_articles:
                if self.store:
                    article_id = self.store.save_article(article)
                    if article_id:
                        self.stats["articles_saved"] += 1
                        new_articles.append((article, article_id))
                else:
                    new_articles.append((article, None))

            # Step 7: Summarize articles
            summaries = {}
            if self.summarizer and new_articles:
                for article, article_id in new_articles:
                    summary = self.summarizer.summarize(article.content, article.title)
                    if summary:
                        summaries[article.url] = summary
                        if self.store and article_id:
                            self.store.update_article(article_id, {"last_summary": summary})
                        self.stats["articles_summarized"] += 1

            # Step 8: Send digest notifications (one message per topic channel)
            if self.notifier and new_articles:
                articles_to_notify = [article for article, _ in new_articles]
                if self.notifier.notify_digest(articles_to_notify, summaries):
                    self.stats["articles_notified"] = len(articles_to_notify)

        except Exception as e:
            logger.error(f"Error in aggregation pipeline: {e}", exc_info=True)
            self.stats["errors"].append(str(e))

        logger.info(f"Pipeline completed. Stats: {self.stats}")
        return self.stats
