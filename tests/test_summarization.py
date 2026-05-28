"""Tests for OpenAI summarization"""

import pytest
import openai
from unittest.mock import MagicMock
from app.src.summarization import Summarizer


@pytest.fixture
def mock_client(mocker):
    client = MagicMock()
    mocker.patch("app.src.summarization.openai.OpenAI", return_value=client)
    return client


@pytest.fixture
def summarizer(mock_client):
    return Summarizer(api_key="test-key")


# --- summarize ---

def test_summarize_returns_none_for_short_content(summarizer, mock_client):
    result = summarizer.summarize("Too short", "Title")
    assert result is None
    mock_client.chat.completions.create.assert_not_called()


def test_summarize_returns_summary(summarizer, mock_client):
    mock_client.chat.completions.create.return_value.choices[0].message.content = "Generated summary."

    result = summarizer.summarize("A" * 100, "Test Title")

    assert result == "Generated summary."
    mock_client.chat.completions.create.assert_called_once()


def test_summarize_passes_title_and_content_to_prompt(summarizer, mock_client):
    mock_client.chat.completions.create.return_value.choices[0].message.content = "Summary."

    summarizer.summarize("A" * 100, "My Article Title")

    call_args = mock_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][1]["content"]
    assert "My Article Title" in prompt


def test_summarize_handles_openai_error(summarizer, mock_client):
    mock_client.chat.completions.create.side_effect = openai.OpenAIError("rate limit")

    result = summarizer.summarize("A" * 100, "Title")
    assert result is None


def test_summarize_handles_unexpected_error(summarizer, mock_client):
    mock_client.chat.completions.create.side_effect = RuntimeError("unexpected")

    result = summarizer.summarize("A" * 100, "Title")
    assert result is None


# --- summarize_update ---

def test_summarize_update_returns_none_for_short_content(summarizer, mock_client):
    result = summarizer.summarize_update("Too short", "Previous summary", "Title")
    assert result is None
    mock_client.chat.completions.create.assert_not_called()


def test_summarize_update_returns_summary(summarizer, mock_client):
    mock_client.chat.completions.create.return_value.choices[0].message.content = "What's new."

    result = summarizer.summarize_update("A" * 100, "Previous summary", "Title")

    assert result == "What's new."


def test_summarize_update_includes_previous_summary_in_prompt(summarizer, mock_client):
    mock_client.chat.completions.create.return_value.choices[0].message.content = "Update."

    summarizer.summarize_update("A" * 100, "The original summary text", "Title")

    call_args = mock_client.chat.completions.create.call_args
    prompt = call_args.kwargs["messages"][1]["content"]
    assert "The original summary text" in prompt
