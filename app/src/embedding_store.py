"""
Vector embedding storage using Qdrant.

Embeds article title + summary using OpenAI text-embedding-3-small and
stores in a Qdrant collection for later semantic search (RAG queries).

Gated by ENABLE_EMBEDDINGS config flag — disabled in prod until tested.
"""

import logging
import uuid
from typing import List, Optional

import openai
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
)

from .models import Article

logger = logging.getLogger(__name__)

COLLECTION_NAME = "news-articles"
VECTOR_SIZE = 1536  # text-embedding-3-small output dimensions
EMBEDDING_MODEL = "text-embedding-3-small"


class EmbeddingStore:
    """
    Stores article embeddings in Qdrant for semantic search.

    Each point stores:
      - vector: embedding of title + summary
      - payload: article metadata for retrieval (id, title, url, topics, source, published_at)
    """

    def __init__(
        self, qdrant_url: str, openai_api_key: str, qdrant_api_key: str = None
    ):
        self.openai_client = openai.OpenAI(api_key=openai_api_key)
        self.qdrant = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Create the Qdrant collection if it doesn't exist."""
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if COLLECTION_NAME not in existing:
            self.qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")

    def _embed(self, text: str) -> List[float]:
        """Generate an embedding vector for the given text."""
        response = self.openai_client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding

    def store(self, article: Article, summary: str = "") -> bool:
        """
        Embed and store an article. Text = title + summary (if available).
        Returns True on success.
        """
        try:
            text = article.title
            if summary:
                text = f"{article.title}\n\n{summary}"

            vector = self._embed(text)

            self.qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    PointStruct(
                        id=str(uuid.uuid5(uuid.NAMESPACE_URL, article.url)),
                        vector=vector,
                        payload={
                            "title": article.title,
                            "url": article.url,
                            "source": article.source,
                            "topics": article.topics,
                            "published_at": article.published_at.isoformat(),
                            "summary": summary,
                        },
                    )
                ],
            )
            logger.debug(f"Embedded and stored: {article.title[:60]}")
            return True

        except Exception as e:
            logger.warning(f"Failed to store embedding for {article.url}: {e}")
            return False

    def search(
        self, query: str, limit: int = 10, topic: Optional[str] = None
    ) -> List[dict]:
        """
        Semantic search over stored articles.

        Args:
            query: Natural language query
            limit: Number of results to return
            topic: Optional topic filter (tech, ai, cyber_security, education)

        Returns:
            List of article payloads ordered by relevance
        """
        try:
            query_vector = self._embed(query)

            search_filter = None
            if topic:
                search_filter = Filter(
                    must=[FieldCondition(key="topics", match=MatchValue(value=topic))]
                )

            results = self.qdrant.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )

            return [{"score": r.score, **r.payload} for r in results]

        except Exception as e:
            logger.error(f"Embedding search failed: {e}")
            return []
