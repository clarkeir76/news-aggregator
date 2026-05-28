"""Configuration management"""

import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class Config:
    """Application configuration loaded from environment variables"""

    def __init__(self):
        # AWS Configuration
        self.aws_region = os.getenv("AWS_REGION", "us-east-1")
        self.dynamodb_table = os.getenv("DYNAMODB_TABLE", "news-articles")
        self.aws_endpoint_url = os.getenv("AWS_ENDPOINT_URL")  # set to http://localhost:4566 for LocalStack

        # OpenAI Configuration
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        # Logging
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Features — ENABLE_SLACK accepts: true | false | log (log = print digest, don't POST)
        slack_mode = os.getenv("ENABLE_SLACK", "true").lower()
        self.enable_slack = slack_mode in ("true", "log")
        self.slack_dry_run = slack_mode == "log"
        self.enable_summarization = os.getenv("ENABLE_SUMMARIZATION", "true").lower() == "true"
        self.enable_persistence = os.getenv("ENABLE_PERSISTENCE", "true").lower() == "true"

        # Limits
        self.max_articles_per_feed = int(os.getenv("MAX_ARTICLES_PER_FEED", "50"))
        self.max_summary_length = int(os.getenv("MAX_SUMMARY_LENGTH", "300"))

    def validate(self) -> bool:
        """Validate required configuration"""
        if not self.openai_api_key:
            logger.warning("OpenAI API key not set - summarization will be disabled")
            self.enable_summarization = False

        return True

    def __repr__(self) -> str:
        return (
            f"Config(aws_region={self.aws_region}, "
            f"dynamodb_table={self.dynamodb_table}, "
            f"openai_model={self.openai_model}, "
            f"enable_slack={self.enable_slack}, "
            f"enable_summarization={self.enable_summarization})"
        )


def get_config() -> Config:
    """Get or create global configuration"""
    if not hasattr(get_config, "_instance"):
        get_config._instance = Config()
        get_config._instance.validate()
    return get_config._instance
