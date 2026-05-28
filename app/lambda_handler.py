"""AWS Lambda handler for news aggregation"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.logging_setup import setup_logging
from src.orchestrator import NewsAggregator
import yaml

# Setup logging
logger = setup_logging("INFO")


def lambda_handler(event, context):
    """
    AWS Lambda handler for news aggregation pipeline.

    Triggered by EventBridge scheduler daily.
    """
    logger.info(f"Lambda invoked with event: {event}")

    try:
        # Get configuration
        config = get_config()

        # Load Slack webhooks from Secrets Manager
        slack_webhooks = _load_slack_webhooks()

        # Initialize aggregator
        aggregator = NewsAggregator(
            feed_config_path="/opt/config/feeds.yaml",
            dynamodb_table=config.dynamodb_table,
            aws_region=config.aws_region,
            openai_api_key=config.openai_api_key,
            slack_webhooks=slack_webhooks,
            enable_summarization=config.enable_summarization,
            enable_slack=config.enable_slack,
            max_articles_per_feed=config.max_articles_per_feed,
        )

        # Run pipeline
        stats = aggregator.run()

        return {
            "statusCode": 200,
            "body": {
                "message": "News aggregation completed successfully",
                "stats": stats,
            },
        }

    except Exception as e:
        logger.error(f"Error in Lambda handler: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": {
                "error": str(e),
            },
        }


def _load_slack_webhooks() -> dict:
    """Load Slack webhook URLs from environment or Secrets Manager"""
    webhooks = {}

    # Try loading from environment first
    topics = ["tech", "education", "ai", "cyber_security"]
    for topic in topics:
        env_var = f"SLACK_WEBHOOK_{topic.upper()}"
        if os.getenv(env_var):
            webhooks[topic] = os.getenv(env_var)

    # In Lambda, would also support loading from Secrets Manager
    # import boto3
    # secrets_client = boto3.client('secretsmanager')
    # secret = secrets_client.get_secret_value(SecretId='news-aggregator/slack-webhooks')

    return webhooks


if __name__ == "__main__":
    # Local testing
    result = lambda_handler({}, None)
    print(result)
