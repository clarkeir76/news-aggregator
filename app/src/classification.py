"""Topic classification — keyword-based and LLM-based classifiers."""

import html
import json
import logging
import re
from typing import List, Optional
import openai

from .models import Article, Topic

logger = logging.getLogger(__name__)

CLASSIFICATION_BATCH_SIZE = 50
DEFAULT_MIN_SIGNIFICANCE = 4
CLUSTER_SNIPPET_CHARS = 200


def _plain_text(text: str) -> str:
    """Strip HTML tags/entities and collapse whitespace from an RSS summary."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


TOPICS = {
    Topic.AI.value: (
        "Strategically significant news where AI is the central subject: frontier or major model releases "  # noqa: E501
        "and version updates (OpenAI, Anthropic, Google DeepMind, Meta, xAI, DeepSeek etc.), "
        "genuine AI breakthroughs or groundbreaking real-world uses of AI, major AI company moves "  # noqa: E501
        "(large funding rounds, acquisitions, significant partnerships, leadership changes at AI labs), "  # noqa: E501
        "AI compute and chip economics, market-moving AI business news (big-tech earnings or "
        "share-price moves driven by AI, shifts in AI capex, major AI revenue deals), AI regulation and policy that changes what organisations can do, "  # noqa: E501
        "significant AI safety incidents, and AI reshaping work or industries at scale. "
        "Also include AI in education ONLY when strategic or groundbreaking: major institutional or "  # noqa: E501
        "government AI policy, large-scale deployments, or significant changes to how people learn "  # noqa: E501
        "or are assessed. "
        "The article must be primarily ABOUT AI itself. EXCLUDE stories where AI or an AI company/executive "  # noqa: E501
        "is only incidental (e.g. espionage, lawsuits or scandals involving a person who works in AI, "  # noqa: E501
        "general business or politics that merely mentions AI). "
        "EXCLUDE: incremental feature updates, minor product launches, individual research papers "  # noqa: E501
        "(unless widely covered), tutorials, opinion pieces, listicles, 'AI-powered' marketing, "  # noqa: E501
        "minor startup news, and anecdotal stories (e.g. a student using AI for homework). "
        "Ask: would a senior technology leader's colleagues and peers be discussing this?"
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

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        enabled_topics: Optional[List[str]] = None,
        min_significance: int = DEFAULT_MIN_SIGNIFICANCE,
        cluster_model: Optional[str] = None,
        classify_model: Optional[str] = None,
    ):
        self.client = openai.OpenAI(api_key=api_key)
        self.model = model
        self.cluster_model = cluster_model or model
        self.classify_model = classify_model or model
        self.min_significance = min_significance
        self.topics = {
            topic: description
            for topic, description in TOPICS.items()
            if enabled_topics is None or topic in enabled_topics
        }
        self._fallback = KeywordClassifier(enabled_topics=enabled_topics)

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
        lines = []
        for num, article in indexed.items():
            snippet = _plain_text(article.content)[:CLUSTER_SNIPPET_CHARS]
            lines.append(f"{num}. {article.title}")
            if snippet:
                lines.append(f"   Summary: {snippet}")

        prompt = f"""Group these news article titles where multiple outlets are reporting on the
EXACT SAME specific news event, incident, or announcement.

Rules:
- Group articles if they are clearly about the same specific event (e.g. the same lawsuit,
  the same breach, the same product launch, the same report) — different headline angles or
  framings of the same event belong in the same group
- Analysis, review, opinion or explainer pieces about the same launch, announcement or event
  belong in the same group as the news reports of it (e.g. a review of a model release is the
  same story as the announcement of that release)
- Use the summaries as well as the titles to decide: shared names, products, numbers and
  companies are strong signals
- Do NOT group articles that merely share a topic or theme (e.g. two different AI lawsuits
  are NOT the same story just because both involve AI and legal action)
- Sharing a company, person or theme is NOT enough to group articles. Two articles that both
  mention Anthropic, Google or OpenAI are different stories unless they report the same
  specific event (e.g. an Anthropic research result and an Anthropic engineer's comments on
  hiring are different stories; two different companies' AI models for cybersecurity are
  different stories)
- To be grouped, articles must report the same specific launch, incident, announcement, result
  or report. If you are unsure, keep them separate; but when the event clearly matches, group
  them even if the framing, outlet or article type (news, analysis, review) differs
- Every article number must appear in exactly one group

Return JSON only: {{"groups": [[1, 4], [2], [3], [5, 6]]}}

Titles:
{chr(10).join(lines)}"""

        response = self.client.chat.completions.create(
            model=self.cluster_model,
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
            if len(members) > 1:
                logger.info(
                    "Cluster: "
                    + " | ".join(f"{a.title} [{a.significance}]" for a in members)
                )
            primary.related_urls = list(
                dict.fromkeys(a.url for a in related if a.url != primary.url)
            )
            scores = [a.significance for a in members if a.significance is not None]
            primary.significance = max(scores) if scores else None
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
        Returns articles that match at least one topic, with topics and significance
        set. The significance threshold is applied later by filter_by_significance,
        after clustering, so a story is judged by its best-scoring article.
        """
        if not articles:
            return []

        try:
            url_to_result = self._classify_batch(articles)
        except Exception as e:
            logger.error(f"LLM classification failed, falling back to keywords: {e}")
            return self._fallback.classify_and_filter(articles)

        matched = []
        for article in articles:
            result = url_to_result.get(article.url)
            if result:
                article.topics, article.significance = result
                matched.append(article)

        discarded = len(articles) - len(matched)
        logger.info(
            f"LLM classification: {len(matched)} matched, {discarded} discarded from {len(articles)} articles"  # noqa: E501
        )
        return matched

    def filter_by_significance(self, articles: List[Article]) -> List[Article]:
        """
        Drop articles (clustered stories) scoring below min_significance. Unscored
        articles are kept. Call after cluster_stories so a cluster's score is the
        highest among its member articles.
        """
        kept = []
        for article in articles:
            score = article.significance
            if score is not None and score < self.min_significance:
                logger.info(
                    f"Dropped (significance {score} < {self.min_significance}): "
                    f"{article.title}"
                )
                continue
            logger.info(f"Kept (significance {score}): {article.title}")
            kept.append(article)
        logger.info(
            f"Significance filter: {len(kept)} kept, {len(articles) - len(kept)} dropped "
            f"(threshold {self.min_significance})"
        )
        return kept

    def _classify_batch(self, articles: List[Article]) -> dict:
        """
        Classify articles in chunks, merge results.
        Returns dict mapping article URL -> (matched topics, significance or None).
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
        """Send one chunk of articles to the LLM. Returns url -> (topics, significance)."""
        indexed = {str(i + 1): article for i, article in enumerate(articles)}

        topic_descriptions = "\n".join(
            f"- {topic}: {description}" for topic, description in self.topics.items()
        )
        topic_names = list(self.topics)
        example = json.dumps(
            {
                "1": {"topics": topic_names[:1], "significance": 5},
                "2": {"topics": topic_names[:2], "significance": 4},
                "3": {"topics": [], "significance": 1},
            }
        )

        article_lines = []
        for num, article in indexed.items():
            summary = _plain_text(article.content)[:300] or "No summary"
            article_lines.append(
                f"{num}. Title: {article.title}\n   Summary: {summary}"
            )

        prompt = f"""Classify these news articles for a senior technology leader in the
education sector. They want to stay up to date on the news their colleagues and peers
will be discussing, not niche or incremental developments. Be highly selective.

Topics and criteria:
{topic_descriptions}

Rules:
- Only assign a topic if the article is primarily ABOUT that topic and clearly fits the
  criteria above, including any EXCLUDE rules. A passing mention of a topic does not count
- An article can match multiple topics
- Exclude general news (politics, sport, entertainment, consumer lifestyle, weather)
- Give each article a significance score from 1 to 5: 5 = major story everyone in the industry will
  discuss, 4 = clearly strategic or groundbreaking, 3 = relevant but routine, 2 = minor or niche,
  1 = not relevant. Use an empty topics list if nothing matches
- Scores must be calibrated harshly: most matching articles should score 2 or 3, and only about
  1 in 20 should score 4 or 5. Score at most 2 for: webinars, event or product promotion,
  vendor tool or product announcements, opinion pieces and explainers, case studies, and
  partnerships involving non-AI companies. Score 4 for market-moving AI business news, such as
  big-tech earnings or share-price moves driven by AI, shifts in AI capex, or major AI revenue
  deals. Reserve 5 for stories like a frontier model release or a major regulatory event
- Respond with valid JSON only, mapping article number to its topics and significance

Example: {example}

Articles:
{chr(10).join(article_lines)}"""

        response = self.client.chat.completions.create(
            model=self.classify_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a news classification assistant for a senior technology leader. "
                        "Be highly selective — only include articles whose main subject matches the stated criteria "  # noqa: E501
                        "and that are strategically significant. "
                        "Respond with valid JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        result = json.loads(response.choices[0].message.content)

        matches = {}
        for num, entry in result.items():
            if num not in indexed:
                continue
            topics, significance = self._parse_entry(entry)
            topics = [t for t in topics if t in self.topics]
            if not topics:
                continue
            matches[indexed[num].url] = (topics, significance)
        return matches

    @staticmethod
    def _parse_entry(entry):
        """Return (topics, significance) from a classifier entry; a bare list has no score."""
        if isinstance(entry, list):
            return entry, None
        if isinstance(entry, dict) and isinstance(entry.get("topics"), list):
            significance = entry.get("significance")
            if not isinstance(significance, (int, float)):
                significance = None
            return entry["topics"], significance
        return [], None


class KeywordClassifier:
    """
    Keyword-based classifier used as a fallback when LLM classification
    is disabled or unavailable.
    """

    def __init__(self, enabled_topics: Optional[List[str]] = None):
        self.enabled_topics = enabled_topics
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
        if enabled_topics is not None:
            self.keywords = {
                topic: words
                for topic, words in self.keywords.items()
                if topic in enabled_topics
            }

    def classify(self, article: Article) -> List[str]:
        text = f"{article.title} {article.content}".lower()
        matched = []
        for topic, keywords in self.keywords.items():
            for keyword in keywords:
                if re.search(r"\b" + re.escape(keyword.lower()) + r"\b", text):
                    matched.append(topic)
                    break
        if matched:
            return matched
        if self.enabled_topics is None or Topic.TECH.value in self.enabled_topics:
            return [Topic.TECH.value]
        return []

    def classify_and_filter(self, articles: List[Article]) -> List[Article]:
        """
        Keyword classifier keeps all articles (no confidence in rejecting),
        unless enabled_topics excludes the tech fallback — then unmatched
        articles are dropped.
        """
        for article in articles:
            article.topics = self.classify(article)
            logger.debug(f"Classified '{article.title}' as {article.topics}")
        return [a for a in articles if a.topics]

    def cluster_stories(self, articles: List[Article]) -> List[Article]:
        """Keyword classifier has no clustering — return articles unchanged."""
        return articles

    def filter_by_significance(self, articles: List[Article]) -> List[Article]:
        """Keyword classifier has no significance score — return articles unchanged."""
        return articles
