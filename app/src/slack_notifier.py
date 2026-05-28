"""Slack notification module"""

import logging
import requests
from datetime import datetime, timezone
from typing import List
from .models import Article

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send digest messages to Slack via incoming webhooks using Block Kit."""

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
                import json

                logger.info(
                    f"[DRY RUN] Digest for #{topic}:\n{json.dumps(message, indent=2)}\n"
                )
            elif not self._send_webhook(self.webhook_urls[topic], message):
                success = False

        return success

    @staticmethod
    def _build_digest(topic: str, articles: List[Article], summaries: dict) -> dict:
        """Build a Slack Block Kit message for one topic digest."""
        count = len(articles)
        noun = "article" if count == 1 else "articles"
        topic_label = topic.replace("_", " ").title()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":newspaper: *{topic_label} Digest — {count} new {noun}* | {timestamp}",  # noqa: E501
                },
            },
            {"type": "divider"},
        ]

        for article in articles:
            text = f"*<{article.url}|{article.title}>*"
            summary = summaries.get(article.url)
            if summary:
                text += f"\n{summary}"
            text += f"\nsource: {article.source} | {article.published_at.strftime('%Y-%m-%d %H:%M UTC')}"  # noqa: E501

            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": text},
                }
            )

        return {
            "unfurl_links": False,
            "unfurl_media": False,
            "blocks": blocks,
        }

    @staticmethod
    def _send_webhook(webhook_url: str, message: dict) -> bool:
        """Send message to Slack incoming webhook"""
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
