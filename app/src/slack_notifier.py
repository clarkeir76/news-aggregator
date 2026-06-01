"""Slack notification module"""

import logging
import requests
from datetime import datetime, timezone
from typing import List
from .models import Article

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send digest messages to Slack via webhooks."""

    def __init__(self, webhook_urls: dict, dry_run: bool = False):
        self.webhook_urls = webhook_urls
        self.dry_run = dry_run

    def notify_digest(self, articles: List[Article], summaries: dict = None) -> bool:
        """
        Send one digest message per topic channel containing all new articles.

        Returns:
            True if all webhooks responded successfully
        """
        summaries = summaries or {}

        by_topic: dict = {}
        for article in articles:
            for topic in article.topics:
                if topic in self.webhook_urls:
                    by_topic.setdefault(topic, []).append(article)

        if not by_topic:
            logger.info("No articles matched configured webhook topics")
            return True

        success = True
        for topic, topic_articles in by_topic.items():
            message = self._build_digest(topic, topic_articles, summaries)
            if self.dry_run:
                logger.info(f"[DRY RUN] Digest for #{topic}:\n{message['payload']}\n")
            elif not self._send_webhook(self.webhook_urls[topic], message):
                success = False

        return success

    MAX_ARTICLES = 20
    MAX_PAYLOAD_CHARS = 7800

    @classmethod
    def _build_digest(
        cls, topic: str, articles: List[Article], summaries: dict
    ) -> dict:
        """Build a plain text payload for a Slack Workflow Builder webhook."""
        total = len(articles)
        capped = articles[: cls.MAX_ARTICLES]
        omitted = total - len(capped)

        noun = "article" if total == 1 else "articles"
        topic_label = topic.replace("_", " ").title()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [f":newspaper: {topic_label} Digest — {total} new {noun} | {timestamp}"]

        for article in capped:
            lines.append(f"\n{article.title}")
            all_urls = [article.url] + (article.related_urls or [])
            for url in all_urls:
                lines.append(url)
            summary = summaries.get(article.url)
            if summary:
                lines.append(summary)
            source = "multiple sources" if article.related_urls else article.source
            lines.append(
                f"source: {source} | {article.published_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )

        if omitted:
            lines.append(f"\n… and {omitted} more article(s) not shown.")

        payload = "\n".join(lines)

        if len(payload) > cls.MAX_PAYLOAD_CHARS:
            payload = payload[: cls.MAX_PAYLOAD_CHARS - 60].rsplit("\n", 1)[0]
            payload += "\n\n… truncated — digest exceeded Slack payload limit."

        return {"payload": payload}

    @staticmethod
    def _send_webhook(webhook_url: str, message: dict) -> bool:
        """Send message to Slack webhook"""
        try:
            response = requests.post(webhook_url, json=message, timeout=10)

            if response.status_code == 200:
                logger.info("Slack digest sent successfully")
                return True
            else:
                logger.error(
                    f"Slack webhook returned {response.status_code}: {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(f"Error sending Slack message: {e}")
            return False
