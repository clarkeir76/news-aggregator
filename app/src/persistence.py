"""DynamoDB persistence module"""

import logging
import uuid
from typing import List, Optional
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

from .models import Article, StoredArticle

logger = logging.getLogger(__name__)


class DynamoDBStore:
    """DynamoDB persistence for articles"""

    def __init__(self, table_name: str, region_name: str = "us-east-1", endpoint_url: str = None):
        self.table_name = table_name
        self.dynamodb = boto3.resource("dynamodb", region_name=region_name, endpoint_url=endpoint_url)
        self.table = self.dynamodb.Table(table_name)

    def save_article(self, article: Article) -> Optional[str]:
        """
        Save article to DynamoDB.

        Returns:
            Article ID (UUID)
        """
        try:
            article_id = str(uuid.uuid4())
            stored_article = StoredArticle.from_article(article, article_id)

            item = stored_article.to_dict()

            # Add partition and sort keys
            item["pk"] = f"ARTICLE#{article_id}"
            item["sk"] = "METADATA"

            # Add GSI keys for querying
            item["url_gsi_pk"] = f"URL#{article.url}"
            item["source_date_gsi_pk"] = f"SOURCE#{article.source}"
            item["source_date_gsi_sk"] = f"DATE#{article.published_at.isoformat()}"

            self.table.put_item(Item=item)
            logger.info(f"Saved article: {article_id}")
            return article_id

        except ClientError as e:
            logger.error(f"Error saving article: {e}")
            return None

    def get_article(self, article_id: str) -> Optional[StoredArticle]:
        """Retrieve article by ID"""
        try:
            response = self.table.get_item(
                Key={"pk": f"ARTICLE#{article_id}", "sk": "METADATA"}
            )

            if "Item" in response:
                return StoredArticle.from_dict(response["Item"])

            return None
        except ClientError as e:
            logger.error(f"Error retrieving article: {e}")
            return None

    def find_by_url(self, url: str) -> Optional[StoredArticle]:
        """Find article by URL"""
        try:
            # Query using GSI
            response = self.table.query(
                IndexName="url_index",
                KeyConditionExpression="url_gsi_pk = :url",
                ExpressionAttributeValues={":url": f"URL#{url}"},
                Limit=1,
            )

            if response["Items"]:
                return StoredArticle.from_dict(response["Items"][0])

            return None
        except ClientError as e:
            logger.error(f"Error finding article by URL: {e}")
            return None

    def find_by_source_date_range(
        self, source: str, start_date: datetime = None, end_date: datetime = None
    ) -> List[StoredArticle]:
        """Find articles by source and date range"""
        try:
            key_condition = "source_date_gsi_pk = :source"
            expression_values = {":source": f"SOURCE#{source}"}

            if start_date or end_date:
                if start_date and end_date:
                    key_condition += " AND source_date_gsi_sk BETWEEN :start AND :end"
                    expression_values[":start"] = f"DATE#{start_date.isoformat()}"
                    expression_values[":end"] = f"DATE#{end_date.isoformat()}"
                elif start_date:
                    key_condition += " AND source_date_gsi_sk >= :start"
                    expression_values[":start"] = f"DATE#{start_date.isoformat()}"
                elif end_date:
                    key_condition += " AND source_date_gsi_sk <= :end"
                    expression_values[":end"] = f"DATE#{end_date.isoformat()}"

            response = self.table.query(
                IndexName="source_date_index",
                KeyConditionExpression=key_condition,
                ExpressionAttributeValues=expression_values,
            )

            return [StoredArticle.from_dict(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(f"Error finding articles by source: {e}")
            return []

    def update_article(self, article_id: str, updates: dict) -> bool:
        """Update article metadata"""
        try:
            # Build update expression
            update_parts = []
            expression_values = {}

            for key, value in updates.items():
                update_parts.append(f"{key} = :{key}")
                expression_values[f":{key}"] = value

            if not update_parts:
                return True

            expression = "SET " + ", ".join(update_parts)

            self.table.update_item(
                Key={"pk": f"ARTICLE#{article_id}", "sk": "METADATA"},
                UpdateExpression=expression,
                ExpressionAttributeValues=expression_values,
            )

            logger.info(f"Updated article: {article_id}")
            return True
        except ClientError as e:
            logger.error(f"Error updating article: {e}")
            return False

    def get_last_run_time(self) -> Optional[datetime]:
        """Retrieve the timestamp of the last successful run."""
        try:
            response = self.table.get_item(Key={"pk": "SYSTEM#config", "sk": "last_run"})
            item = response.get("Item")
            if item:
                return datetime.fromisoformat(item["timestamp"])
            return None
        except ClientError as e:
            logger.error(f"Error retrieving last run time: {e}")
            return None

    def save_last_run_time(self, dt: datetime) -> None:
        """Store the timestamp of a successful run."""
        try:
            self.table.put_item(Item={
                "pk": "SYSTEM#config",
                "sk": "last_run",
                "timestamp": dt.isoformat(),
            })
        except ClientError as e:
            logger.error(f"Error saving last run time: {e}")

    def get_recent_articles(self, limit: int = 100) -> List[StoredArticle]:
        """Get recent articles"""
        try:
            response = self.table.scan(
                Limit=limit,
            )

            return [StoredArticle.from_dict(item) for item in response.get("Items", [])]
        except ClientError as e:
            logger.error(f"Error retrieving recent articles: {e}")
            return []
