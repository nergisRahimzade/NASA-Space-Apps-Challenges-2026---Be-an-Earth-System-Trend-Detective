"""Tests for ESD-D04-BE: explain() caches answers so a repeat call skips the API."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from earth_system_trend import explain as explain_mod
from earth_system_trend.explain import explain, fallback_text

RESULT = {
    "region": "Phoenix study area",
    "period": {"start": "2003-01", "end": "2024-12"},
    "series": [],
    "trend": {"slope": 0.006, "p": 0.0001, "tau": 0.16, "trend": "increasing"},
    "explanation": None,
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(explain_mod.time, "sleep", lambda _s: None)


def _reply(text):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text))])


def _client(*side_effects):
    client = MagicMock()
    client.chat.completions.create.side_effect = list(side_effects)
    return client


def _timeout():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
    return openai.APITimeoutError(request=request)


def test_repeat_call_skips_the_api():
    first = _client(_reply("Nights got warmer."))
    assert explain(RESULT, client=first) == "Nights got warmer."

    second = _client()  # would fail if it were called
    assert explain(RESULT, client=second) == "Nights got warmer."
    second.chat.completions.create.assert_not_called()


def test_cached_answer_is_used_even_without_a_key():
    explain(RESULT, client=_client(_reply("Nights got warmer.")))
    assert explain(RESULT) == "Nights got warmer."  # conftest removed the key


def test_different_numbers_are_not_served_from_cache():
    explain(RESULT, client=_client(_reply("Nights got warmer.")))
    changed = {**RESULT, "trend": {**RESULT["trend"], "slope": 0.5}}
    client = _client(_reply("A different answer."))
    assert explain(changed, client=client) == "A different answer."
    assert client.chat.completions.create.call_count == 1


def test_different_model_is_not_served_from_cache():
    explain(RESULT, client=_client(_reply("Nights got warmer.")), model="model-a")
    client = _client(_reply("From model b."))
    assert explain(RESULT, client=client, model="model-b") == "From model b."


def test_fallback_is_not_cached():
    failing = _client(_timeout(), _timeout())
    assert explain(RESULT, client=failing) == fallback_text(RESULT)

    working = _client(_reply("Nights got warmer."))
    assert explain(RESULT, client=working) == "Nights got warmer."
    assert working.chat.completions.create.call_count == 1


def test_cache_file_is_written_where_settings_say(tmp_path, monkeypatch):
    path = tmp_path / "custom" / "cache.json"
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(path))
    explain(RESULT, client=_client(_reply("Nights got warmer.")))
    assert path.exists()


def test_unwritable_cache_still_returns_the_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(tmp_path))  # a folder: writes fail
    assert explain(RESULT, client=_client(_reply("Still fine."))) == "Still fine."
