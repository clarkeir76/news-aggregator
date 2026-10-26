"""Tests for configuration parsing"""

from app.src.config import Config


def test_enabled_topics_unset_means_all(monkeypatch):
    monkeypatch.delenv("ENABLED_TOPICS", raising=False)
    assert Config().enabled_topics is None


def test_enabled_topics_empty_means_all(monkeypatch):
    monkeypatch.setenv("ENABLED_TOPICS", "")
    assert Config().enabled_topics is None


def test_enabled_topics_parses_list(monkeypatch):
    monkeypatch.setenv("ENABLED_TOPICS", "ai, Tech")
    assert Config().enabled_topics == ["ai", "tech"]


def test_enabled_topics_ignores_unknown(monkeypatch):
    monkeypatch.setenv("ENABLED_TOPICS", "ai,sport")
    assert Config().enabled_topics == ["ai"]


def test_enabled_topics_all_unknown_falls_back_to_all(monkeypatch):
    monkeypatch.setenv("ENABLED_TOPICS", "sport")
    assert Config().enabled_topics is None
