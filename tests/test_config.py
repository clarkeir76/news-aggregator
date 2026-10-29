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


def test_min_significance_defaults_to_four(monkeypatch):
    monkeypatch.delenv("MIN_SIGNIFICANCE", raising=False)
    assert Config().min_significance == 4


def test_min_significance_parses_env(monkeypatch):
    monkeypatch.setenv("MIN_SIGNIFICANCE", "3")
    assert Config().min_significance == 3


def test_cluster_model_unset_is_none(monkeypatch):
    monkeypatch.delenv("CLUSTER_MODEL", raising=False)
    assert Config().cluster_model is None


def test_cluster_model_empty_is_none(monkeypatch):
    monkeypatch.setenv("CLUSTER_MODEL", "")
    assert Config().cluster_model is None


def test_cluster_model_parses_env(monkeypatch):
    monkeypatch.setenv("CLUSTER_MODEL", "gpt-4.1")
    assert Config().cluster_model == "gpt-4.1"


def test_classify_model_unset_is_none(monkeypatch):
    monkeypatch.delenv("CLASSIFY_MODEL", raising=False)
    assert Config().classify_model is None


def test_classify_model_parses_env(monkeypatch):
    monkeypatch.setenv("CLASSIFY_MODEL", "gpt-4.1")
    assert Config().classify_model == "gpt-4.1"
