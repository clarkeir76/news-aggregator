"""Data models for news articles"""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Optional
import hashlib
from enum import Enum


class Topic(str, Enum):
    """Supported article topics"""

    TECH = "tech"
    EDUCATION = "education"
    AI = "ai"
    CYBER_SECURITY = "cyber_security"

    @classmethod
    def all_topics(cls) -> List[str]:
        """Return all supported topics"""
        return [topic.value for topic in cls]


@dataclass
class Article:
    """Normalized article schema"""

    title: str
    source: str
    url: str
    published_at: datetime
    content: str
    topics: List[str] = field(default_factory=list)
    content_hash: Optional[str] = None
    canonical_url: Optional[str] = None
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        """Compute content hash if not provided"""
        if not self.content_hash and self.content:
            self.content_hash = self._compute_hash(self.content)

    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute SHA256 hash of content"""
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        data["fetched_at"] = self.fetched_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        """Create from dictionary"""
        data = data.copy()
        data["published_at"] = (
            datetime.fromisoformat(data["published_at"])
            if isinstance(data["published_at"], str)
            else data["published_at"]
        )
        data["fetched_at"] = (
            datetime.fromisoformat(data["fetched_at"])
            if isinstance(data["fetched_at"], str)
            else data["fetched_at"]
        )
        return cls(**data)


@dataclass
class StoredArticle(Article):
    """Article stored in DynamoDB with metadata"""

    article_id: Optional[str] = None
    first_seen_at: datetime = field(default_factory=datetime.utcnow)
    last_seen_at: datetime = field(default_factory=datetime.utcnow)
    last_summary: Optional[str] = None
    update_count: int = 0
    is_new: bool = True

    def to_dict(self) -> dict:
        """Convert to dictionary for DynamoDB storage"""
        data = asdict(self)
        data["published_at"] = self.published_at.isoformat()
        data["fetched_at"] = self.fetched_at.isoformat()
        data["first_seen_at"] = self.first_seen_at.isoformat()
        data["last_seen_at"] = self.last_seen_at.isoformat()
        return data

    @classmethod
    def from_article(cls, article: Article, article_id: str = None) -> "StoredArticle":
        """Create from Article"""
        return cls(
            title=article.title,
            source=article.source,
            url=article.url,
            published_at=article.published_at,
            content=article.content,
            topics=article.topics,
            content_hash=article.content_hash,
            canonical_url=article.canonical_url,
            fetched_at=article.fetched_at,
            article_id=article_id,
        )
