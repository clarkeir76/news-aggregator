"""Main orchestration module"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
        feed_timeout: int = 20,
        max_article_age_hours: int = 24,
        last_run_file: str = "logs/.last_run",
    ):
        self.feed_config_path = feed_config_path
        self.max_concurrent_feeds = max_concurrent_feeds
        self.max_concurrent_summarizations = max_concurrent_summarizations
        self.max_article_age_hours = max_article_age_hours
        self.last_run_file = last_run_file

        # Store must be initialised before cutoff calculation (last run may come from DynamoDB)
        self.store = None
        if enable_persistence and dynamodb_table:
            self.store = DynamoDBStore(
                table_name=dynamodb_table,
                region_name=aws_region,
                endpoint_url=aws_endpoint_url,
            )

        cutoff = self._calculate_cutoff()
        logger.info(f"Article cutoff: {cutoff.isoformat() if cutoff else 'none'}")

        self.ingester = RSSIngester(
            max_articles_per_feed=max_articles_per_feed,
            max_concurrent_feeds=max_concurrent_feeds,
            timeout=feed_timeout,
            cutoff=cutoff,
        )

        self.classifier = (
            LLMClassifier(api_key=openai_api_key)
            if enable_llm_classification and openai_api_key
            else KeywordClassifier()
        )

        self.content_extractor = ContentExtractor()
        self.deduplicator = Deduplicator()

        self.summarizer = None
        if enable_summarization and openai_api_key:
            self.summarizer = Summarizer(api_key=openai_api_key)

        self.notifier = None
        if enable_slack and slack_webhooks:
            self.notifier = SlackNotifier(
                webhook_urls=slack_webhooks, dry_run=slack_dry_run
            )

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
        run_start = datetime.now(timezone.utc)
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
            logger.info(
                f"Ingested {len(articles)} articles from {len(feed_configs)} feeds"
            )

            # Step 2: Classify and filter
            articles = self.classifier.classify_and_filter(articles)
            self.stats["articles_classified"] = len(articles)
            logger.info(f"{len(articles)} articles matched our topics")

            # Step 3: Cluster same-story articles across sources
            if hasattr(self.classifier, "cluster_stories"):
                articles = self.classifier.cluster_stories(articles)
                self.stats["articles_classified"] = len(articles)

            # Step 4: Fetch full article text (matched articles only, concurrent)
            articles = self._enrich_content(articles)

            # Step 5: Deduplicate
            existing_articles = (
                self.store.get_recent_articles(limit=1000) if self.store else []
            )
            logger.info(
                f"Retrieved {len(existing_articles)} existing articles for deduplication"
            )
            unique_articles, dedup_stats = self.deduplicator.deduplicate(
                articles, existing_articles
            )
            self.stats.update(dedup_stats)

            # Step 6: Persist
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

        if not self.stats["errors"]:
            self._save_last_run()

        elapsed = (datetime.now(timezone.utc) - run_start).total_seconds()
        ingested = self.stats.get("articles_ingested", 0)
        classified = self.stats.get("articles_classified", 0)
        rejected = ingested - classified
        duplicates = (
            self.stats.get("url_duplicates", 0)
            + self.stats.get("content_hash_duplicates", 0)
            + self.stats.get("title_fuzzy_duplicates", 0)
        )
        unique = self.stats.get("unique_output", classified)
        feeds_ok = self.stats.get("successful_feeds", 0)
        feeds_total = self.stats.get("total_feeds", 0)
        feeds_failed = self.stats.get("failed_feeds", 0)
        feeds_empty = self.stats.get("feeds_no_new_articles", 0)

        logger.info(
            f"Run complete in {elapsed:.1f}s | "
            f"Feeds: {feeds_ok}/{feeds_total} ok, {feeds_empty} no new articles, {feeds_failed} failed | "  # noqa: E501
            f"Articles: {ingested} ingested, {classified} matched, {rejected} rejected | "
            f"Content: {classified} fetched | "
            f"Dedup: {unique} unique, {duplicates} duplicate(s) | "
            f"Summarised: {self.stats.get('articles_summarized', 0)} | "
            f"Notified: {self.stats.get('articles_notified', 0)}"
        )
        return self.stats

    def _enrich_content(self, articles: List[Article]) -> List[Article]:
        """Fetch full article text concurrently for all matched articles."""
        if not articles:
            return []

        def fetch(article: Article) -> Article:
            article.content = self.content_extractor.get_content(
                article.url, article.content
            )
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

    def _calculate_cutoff(self) -> Optional[datetime]:
        """
        Returns the most recent of:
          - now minus max_article_age_hours (hard cap)
          - the last successful run time (from file or DynamoDB)

        This means hourly runs only fetch the last hour; if the pipeline
        hasn't run for 2 days it still caps at max_article_age_hours.
        """
        now = datetime.now(timezone.utc)

        age_cutoff = (
            now - timedelta(hours=self.max_article_age_hours)
            if self.max_article_age_hours > 0
            else None
        )

        last_run = self._load_last_run()

        if last_run and age_cutoff:
            return max(last_run, age_cutoff)  # most recent = tightest window
        return last_run or age_cutoff

    def _load_last_run(self) -> Optional[datetime]:
        """Load last successful run time — DynamoDB if available, otherwise file."""
        if self.store:
            ts = self.store.get_last_run_time()
            if ts:
                return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts

        try:
            text = Path(self.last_run_file).read_text().strip()
            dt = datetime.fromisoformat(text)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
        except (FileNotFoundError, ValueError):
            return None

    def _save_last_run(self) -> None:
        """Save successful run time — DynamoDB if available, always file."""
        now = datetime.now(timezone.utc)

        if self.store:
            self.store.save_last_run_time(now)

        try:
            Path(self.last_run_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.last_run_file).write_text(now.isoformat())
        except OSError as e:
            logger.warning(f"Could not write last run file: {e}")

    def _summarise(self, new_articles: list) -> dict:
        """Summarise new articles concurrently. Returns dict of url -> summary."""
        if not self.summarizer or not new_articles:
            return {}

        def summarise_one(pair):
            article, article_id = pair
            summary = self.summarizer.summarize(
                article.content, article.title, article.topics
            )
            if summary and self.store and article_id:
                self.store.update_article(article_id, {"last_summary": summary})
            return article.url, summary

        summaries = {}
        results = []
        with ThreadPoolExecutor(
            max_workers=self.max_concurrent_summarizations
        ) as executor:
            futures = {
                executor.submit(summarise_one, pair): pair for pair in new_articles
            }
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
