"""Topic classification module"""

import logging
from typing import List, Set
from .models import Article, Topic

logger = logging.getLogger(__name__)


class KeywordClassifier:
    """Keyword-based topic classifier"""

    def __init__(self):
        """Initialize keyword patterns for each topic"""
        self.keywords = {
            Topic.AI.value: [
                "artificial intelligence",
                "machine learning",
                "neural network",
                "deep learning",
                "gpt",
                "llm",
                "large language model",
                "transformer",
                "ai",
                "generative ai",
                "prompt",
                "embeddings",
            ],
            Topic.TECH.value: [
                "technology",
                "software",
                "app",
                "startup",
                "github",
                "programming",
                "code",
                "developer",
                "api",
                "cloud",
                "data",
                "computing",
                "web",
                "mobile",
                "internet",
            ],
            Topic.CYBER_SECURITY.value: [
                "security",
                "cybersecurity",
                "cyber security",
                "hacker",
                "breach",
                "vulnerability",
                "malware",
                "ransomware",
                "encryption",
                "authentication",
                "cyber attack",
                "data breach",
                "privacy",
            ],
            Topic.EDUCATION.value: [
                "education",
                "school",
                "university",
                "student",
                "learning",
                "teacher",
                "course",
                "training",
                "classroom",
                "college",
                "academic",
                "curriculum",
                "degree",
            ],
        }

    def classify(self, article: Article) -> List[str]:
        """
        Classify article into topics based on keywords.

        Returns:
            List of matched topics
        """
        if article.topics:
            # If topics already provided (from feed config), use them
            return article.topics

        text = f"{article.title} {article.content}".lower()
        matched_topics = []

        for topic, keywords in self.keywords.items():
            for keyword in keywords:
                if keyword.lower() in text:
                    matched_topics.append(topic)
                    break  # Match topic once per article

        # Default to 'tech' if no match found
        if not matched_topics:
            matched_topics = [Topic.TECH.value]

        return matched_topics

    def classify_articles(self, articles: List[Article]) -> List[Article]:
        """Classify multiple articles"""
        for article in articles:
            article.topics = self.classify(article)
            logger.debug(f"Classified '{article.title}' as {article.topics}")

        return articles
