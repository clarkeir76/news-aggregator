"""Topic classification — keyword-based and LLM-based classifiers."""

import json
import logging
import re
from typing import List
import openai

from .models import Article, Topic

logger = logging.getLogger(__name__)

CLASSIFICATION_BATCH_SIZE = 50

TOPICS = {
    Topic.AI.value: "artificial intelligence, machine learning, LLMs, generative AI, AI research, AI products and companies",
    Topic.TECH.value: "technology, software, startups, programming, cloud, hardware, developer tools (not specifically AI)",
    Topic.CYBER_SECURITY.value: "security breaches, vulnerabilities, hacking, malware, ransomware, privacy, cybercrime",
    Topic.EDUCATION.value: "schools, universities, students, teaching, educational policy, EdTech, academic research",
}


class LLMClassifier:
    """
    Classifies and filters articles using a single batched LLM call.
    Falls back to KeywordClassifier if the API call fails.
    """

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self._fallback = KeywordClassifier()

    def classify_and_filter(self, articles: List[Article]) -> List[Article]:
        """
        Classify a batch of articles in one LLM call.
        Returns only articles that match at least one topic, with topics set.
        """
        if not articles:
            return []

        try:
            url_to_topics = self._classify_batch(articles)
        except Exception as e:
            logger.error(f"LLM classification failed, falling back to keywords: {e}")
            return self._fallback.classify_and_filter(articles)

        matched = []
        for article in articles:
            topics = url_to_topics.get(article.url, [])
            if topics:
                article.topics = topics
                matched.append(article)

        discarded = len(articles) - len(matched)
        logger.info(
            f"LLM classification: {len(matched)} matched, {discarded} discarded from {len(articles)} articles"
        )
        return matched

    def _classify_batch(self, articles: List[Article]) -> dict:
        """
        Classify articles in chunks, merge results.
        Returns dict mapping article URL -> list of matched topics.
        """
        all_results = {}
        chunks = [
            articles[i : i + CLASSIFICATION_BATCH_SIZE]
            for i in range(0, len(articles), CLASSIFICATION_BATCH_SIZE)
        ]
        logger.info(f"Classifying {len(articles)} articles in {len(chunks)} batch(es)")
        for chunk in chunks:
            all_results.update(self._classify_chunk(chunk))
        return all_results

    def _classify_chunk(self, articles: List[Article]) -> dict:
        """Send one chunk of articles to the LLM. Returns url -> topics dict."""
        indexed = {str(i + 1): article for i, article in enumerate(articles)}

        topic_descriptions = "\n".join(
            f"- {topic}: {description}" for topic, description in TOPICS.items()
        )

        article_lines = []
        for num, article in indexed.items():
            summary = (
                article.content[:300] if article.content else ""
            ).strip() or "No summary"
            article_lines.append(
                f"{num}. Title: {article.title}\n   Summary: {summary}"
            )

        prompt = f"""Classify these news articles for a news aggregator.

Topics:
{topic_descriptions}

Rules:
- Only assign a topic if the article clearly fits
- An article can match multiple topics
- If the article is general news (politics, sport, entertainment, weather) that doesn't fit any topic, exclude it
- Respond with valid JSON only, mapping article number to its matched topics (empty list = no match)

Example: {{"1": ["tech"], "2": ["ai", "tech"], "3": [], "4": ["education", "cyber_security"]}}

Articles:
{chr(10).join(article_lines)}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a news classification assistant. Respond with valid JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        return {
            indexed[num].url: [t for t in topics if t in TOPICS]
            for num, topics in result.items()
            if num in indexed and isinstance(topics, list) and topics
        }


class KeywordClassifier:
    """
    Keyword-based classifier used as a fallback when LLM classification
    is disabled or unavailable.
    """

    def __init__(self):
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
        text = f"{article.title} {article.content}".lower()
        matched = []
        for topic, keywords in self.keywords.items():
            for keyword in keywords:
                if re.search(r"\b" + re.escape(keyword.lower()) + r"\b", text):
                    matched.append(topic)
                    break
        return matched or [Topic.TECH.value]

    def classify_articles(self, articles: List[Article]) -> List[Article]:
        for article in articles:
            article.topics = self.classify(article)
            logger.debug(f"Classified '{article.title}' as {article.topics}")
        return articles

    def classify_and_filter(self, articles: List[Article]) -> List[Article]:
        """Keyword classifier keeps all articles (no confidence in rejecting)."""
        return self.classify_articles(articles)
