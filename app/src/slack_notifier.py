"""Slack notification module"""

import logging
import requests
from typing import Optional, List
from .models import Article

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Send messages to Slack via webhooks"""

    def __init__(self, webhook_urls: dict):
        """
        Initialize with webhook URLs per topic.

        Args:
            webhook_urls: Dict mapping topic -> webhook URL
        """
        self.webhook_urls = webhook_urls

    def notify(
        self,
        article: Article,
        summary: str = "",
        is_update: bool = False,
    ) -> bool:
        """
        Send article notification to appropriate Slack channel(s).

        Args:
            article: Article to notify about
            summary: Summary text
            is_update: Whether this is an update to existing article

        Returns:
            True if notification sent successfully
        """
        success = True

        for topic in article.topics:
            if topic in self.webhook_urls:
                webhook_url = self.webhook_urls[topic]
                message = self._build_message(article, summary, is_update)

                if not self._send_webhook(webhook_url, message):
                    success = False

        return success

    def notify_batch(
        self,
        articles: List[Article],
        summaries: dict = None,
        is_updates: dict = None,
    ) -> bool:
        """
        Send multiple article notifications.

        Args:
            articles: List of articles
            summaries: Dict mapping article URL -> summary
            is_updates: Dict mapping article URL -> is_update flag

        Returns:
            True if all notifications sent successfully
        """
        summaries = summaries or {}
        is_updates = is_updates or {}
        success = True

        for article in articles:
            summary = summaries.get(article.url, "")
            is_update = is_updates.get(article.url, False)

            if not self.notify(article, summary, is_update):
                success = False

        return success

    @staticmethod
    def _build_message(article: Article, summary: str = "", is_update: bool = False) -> dict:
        """Build Slack message payload"""
        emoji = "🔄" if is_update else "📰"
        header = f"{emoji} {'UPDATE: ' if is_update else ''}{article.title}"

        fields = [
            {
                "title": "Source",
                "value": article.source,
                "short": True,
            },
            {
                "title": "Topics",
                "value": ", ".join(article.topics),
                "short": True,
            },
            {
                "title": "Published",
                "value": article.published_at.strftime("%Y-%m-%d %H:%M UTC"),
                "short": True,
            },
        ]

        if summary:
            fields.append(
                {
                    "title": "Summary",
                    "value": summary,
                    "short": False,
                }
            )

        message = {
            "username": "News Aggregator",
            "icon_emoji": ":newspaper:",
            "attachments": [
                {
                    "color": "#0099ff" if is_update else "#36a64f",
                    "title": header,
                    "title_link": article.url,
                    "fields": fields,
                    "footer": "News Aggregator System",
                    "ts": int(article.published_at.timestamp()),
                }
            ],
        }

        return message

    @staticmethod
    def _send_webhook(webhook_url: str, message: dict) -> bool:
        """Send message to Slack webhook"""
        try:
            response = requests.post(
                webhook_url,
                json=message,
                timeout=10,
            )

            if response.status_code == 200:
                logger.info("Slack message sent successfully")
                return True
            else:
                logger.error(
                    f"Slack webhook returned {response.status_code}: {response.text}"
                )
                return False

        except requests.RequestException as e:
            logger.error(f"Error sending Slack message: {e}")
            return False
