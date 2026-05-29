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
    Topic.AI.value: (
        "Artificial intelligence and machine learning: LLMs, generative AI, AI research breakthroughs, "  # noqa: E501
        "new AI products and tools, AI company news (OpenAI, Anthropic, Google DeepMind etc.), "
        "AI regulation and policy, AI's impact on work and industries. "
        "Cast a wide net — include most AI stories."
    ),
    Topic.TECH.value: (
        "Technology news relevant to a software engineering leader: new developer tools and frameworks, "  # noqa: E501
        "cloud platform updates, software engineering practices, startup launches and significant funding rounds, "  # noqa: E501
        "technical innovations worth discussing at CTO or engineering manager level. "
        "EXCLUDE: consumer product deals and discounts (e.g. '50% off TV'), gaming releases and reviews, "  # noqa: E501
        "home entertainment, fitness gadgets, 'best buy' recommendations, and any story whose primary "  # noqa: E501
        "angle is a price reduction or retail promotion rather than the technology itself."
    ),
    Topic.CYBER_SECURITY.value: (
        "Cybersecurity news: data breaches, ransomware attacks, software vulnerabilities and patches, "  # noqa: E501
        "hacking incidents, privacy violations, security policy and regulation, nation-state cyber activity. "  # noqa: E501
        "Include most cybersecurity stories — cast a wide net."
    ),
    Topic.EDUCATION.value: (
        "Post-18 education and skills in the UK and globally: university admissions and policy, degree programmes, "  # noqa: E501
        "apprenticeships (especially UK levy-funded), professional qualifications and development, vocational training. "  # noqa: E501
        "Government policy on higher education, skills funding, and apprenticeships. "
        "Youth unemployment and the NEET issue (18-24 year olds not in employment, education or training). "  # noqa: E501
        "EdTech platforms for adult and professional learning. UK stories are priority but include major "  # noqa: E501
        "global stories on higher education or skills gaps. "
        "EXCLUDE: primary school and secondary school stories unless directly about the transition to post-18 education. "  # noqa: E501
        "EXCLUDE: stories set in educational institutions that are really about something else "
        "(conflict, religion, disasters, sport). "
        "Ask: would a UK post-18 education executive find this directly relevant to their market?"
    ),
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

    def cluster_stories(self, articles: List[Article]) -> List[Article]:
        """
        Group articles covering the same story. Returns a reduced list where
        each cluster is represented by the article with the most content;
        the other URLs are stored in article.related_urls.
        """
        if len(articles) <= 1:
            return articles

        try:
            return self._cluster(articles)
        except Exception as e:
            logger.warning(f"Story clustering failed, skipping: {e}")
            return articles

    def _cluster(self, articles: List[Article]) -> List[Article]:
        indexed = {str(i + 1): article for i, article in enumerate(articles)}
        lines = [f"{num}. {article.title}" for num, article in indexed.items()]

        prompt = f"""Group these news article titles where multiple outlets are reporting on the
EXACT SAME specific news event, incident, or announcement.

Rules:
- Only group articles if they are clearly about the same specific event (e.g. the same breach,
  the same product launch, the same report)
- Do NOT group articles that merely share a topic or theme (e.g. two different AI security stories
  are NOT the same story even if both involve AI and security)
- Each group should have a maximum of 3 articles
- When in doubt, keep articles separate — it is better to under-cluster than over-cluster
- Every article number must appear in exactly one group

Return JSON only: {{"groups": [[1, 4], [2], [3], [5, 6]]}}

Titles:
{chr(10).join(lines)}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a strict news deduplication assistant. Only group articles reporting on the exact same specific event. Respond with valid JSON only.",  # noqa: E501
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)
        groups = result.get("groups", [])

        merged = []
        for group in groups:
            members = [indexed[str(n)] for n in group if str(n) in indexed]
            if not members:
                continue
            primary = max(members, key=lambda a: len(a.content or ""))
            related = [a for a in members if a is not primary]
            primary.related_urls = [a.url for a in related]
            merged.append(primary)

        clustered = len(articles) - len(merged)
        if clustered > 0:
            logger.info(
                f"Story clustering: {len(articles)} articles → {len(merged)} stories "
                f"({clustered} merged)"
            )
        return merged

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
            f"LLM classification: {len(matched)} matched, {discarded} discarded from {len(articles)} articles"  # noqa: E501
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
        logger.info(
            f"Classifying {len(articles)} articles in {len(chunks)} batch(es)"
        )  # noqa: E501
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

        prompt = f"""Classify these news articles for a UK software engineering leader who works in the  # noqa: E501
commercial post-18 education sector (apprenticeships, university degrees, professional development).
Select articles that are professionally relevant or genuinely newsworthy at a strategic level.

Topics and criteria:
{topic_descriptions}

Rules:
- Only assign a topic if the article clearly fits the criteria above, including any EXCLUDE rules
- An article can match multiple topics
- Exclude general news (politics, sport, entertainment, consumer lifestyle, weather)
- Respond with valid JSON only, mapping article number to its matched topics (empty list = no match)

Example: {{"1": ["tech"], "2": ["ai", "tech"], "3": [], "4": ["education", "cyber_security"]}}

Articles:
{chr(10).join(article_lines)}"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a news classification assistant for a senior technology and education professional. "  # noqa: E501
                        "Be selective — only include articles that are genuinely relevant to the stated criteria. "  # noqa: E501
                        "Respond with valid JSON only."
                    ),
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

    def classify_and_filter(self, articles: List[Article]) -> List[Article]:
        """Keyword classifier keeps all articles (no confidence in rejecting)."""
        for article in articles:
            article.topics = self.classify(article)
            logger.debug(f"Classified '{article.title}' as {article.topics}")
        return articles

    def cluster_stories(self, articles: List[Article]) -> List[Article]:
        """Keyword classifier has no clustering — return articles unchanged."""
        return articles
