"""Tests for ESD-D04-BE: config.py reads settings from the environment."""

from pathlib import Path

from earth_system_trend.config import (
    DEFAULT_MODEL,
    DEFAULT_RESULTS_PATH,
    DEFAULT_TIMEOUT_S,
    get_settings,
)


def test_defaults_when_nothing_is_set(monkeypatch):
    for name in ("RESULTS_PATH", "OPENAI_TIMEOUT_S", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.results_path == Path(DEFAULT_RESULTS_PATH)
    assert settings.openai_api_key is None
    assert settings.openai_model == DEFAULT_MODEL
    assert settings.openai_timeout_s == DEFAULT_TIMEOUT_S
    assert settings.log_level == "INFO"


def test_values_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", "results/results.json")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", "some-model")
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "30")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    settings = get_settings()
    assert settings.results_path == Path("results/results.json")
    assert settings.openai_api_key == "sk-test"
    assert settings.openai_model == "some-model"
    assert settings.openai_timeout_s == 30.0
    assert settings.log_level == "DEBUG"


def test_empty_key_counts_as_missing(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    assert get_settings().openai_api_key is None


def test_bad_timeout_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "fast")
    assert get_settings().openai_timeout_s == DEFAULT_TIMEOUT_S


def test_settings_are_read_fresh_each_call(monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", "a.json")
    first = get_settings()
    monkeypatch.setenv("RESULTS_PATH", "b.json")
    assert first.results_path == Path("a.json")
    assert get_settings().results_path == Path("b.json")
