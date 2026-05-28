"""OpenAI summarization module"""

import logging
from typing import Optional
import openai

logger = logging.getLogger(__name__)


class Summarizer:
    """OpenAI-based text summarization"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", max_tokens: int = 150):
        self.model = model
        self.max_tokens = max_tokens
        self.client = openai.OpenAI(api_key=api_key)

    def summarize(self, content: str, title: str = "", topics: list = None) -> Optional[str]:
        """
        Generate a concise summary of content.

        Returns:
            Summary text or None if error
        """
        if not content or len(content) < 50:
            logger.warning("Content too short to summarize")
            return None

        try:
            prompt = f"""Summarize the following news article in 1-2 sentences.
Include:
- What happened
- Why it matters

Title: {title}

Content: {content[:2000]}

Summary:"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news summarization expert. Create clear, concise summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.max_tokens,
                temperature=0.5,
            )

            summary = response.choices[0].message.content.strip()
            topic_str = f" [{', '.join(topics)}]" if topics else ""
            logger.info(f"Generated summary{topic_str} ({len(summary)} chars)")
            return summary

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during summarization: {e}")
            return None

    def summarize_update(
        self, new_content: str, old_summary: str, title: str = ""
    ) -> Optional[str]:
        """
        Summarize an updated article, highlighting what's new.

        Returns:
            Update summary or None if error
        """
        if not new_content or len(new_content) < 50:
            return None

        try:
            prompt = f"""This news article has been updated. Summarize only the new information in 1-2 sentences.

Previous summary: {old_summary}

New content: {new_content[:2000]}

What's new:"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a news summarization expert. Focus on what is new and different.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=150,
                temperature=0.5,
            )

            summary = response.choices[0].message.content.strip()
            logger.info(f"Generated update summary ({len(summary)} chars)")
            return summary

        except openai.OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during summarization: {e}")
            return None
