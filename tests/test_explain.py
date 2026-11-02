"""Tests for ESD-D03-BE: explain() works and fails safely. No network calls."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import openai
import pytest

from earth_system_trend import explain as explain_mod
from earth_system_trend.explain import explain, fallback_text

RESULT = {
    "region": "California",
    "period": "2000-2023",
    "series": [],
    "trend": {"slope": 0.031, "p": 0.002, "tau": 0.41, "trend": "increasing"},
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


def _request():
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def test_returns_model_text():
    client = _client(_reply("  Temperatures rose.  "))
    assert explain(RESULT, client=client) == "Temperatures rose."
    kwargs = client.chat.completions.create.call_args.kwargs
    assert "timeout" in kwargs
    assert '"slope": 0.031' in kwargs["messages"][1]["content"]


def test_retries_once_on_timeout_then_succeeds():
    client = _client(openai.APITimeoutError(request=_request()), _reply("ok"))
    assert explain(RESULT, client=client) == "ok"
    assert client.chat.completions.create.call_count == 2


def test_falls_back_after_two_transient_failures():
    err = openai.APIConnectionError(request=_request())
    client = _client(err, err)
    text = explain(RESULT, client=client)
    assert client.chat.completions.create.call_count == 2
    assert text == fallback_text(RESULT)


def test_does_not_retry_auth_error():
    response = httpx.Response(401, request=_request())
    err = openai.AuthenticationError("bad key", response=response, body=None)
    client = _client(err)
    assert explain(RESULT, client=client) == fallback_text(RESULT)
    assert client.chat.completions.create.call_count == 1


def test_empty_reply_is_retried_then_falls_back():
    client = _client(_reply(""), _reply(None))
    assert explain(RESULT, client=client) == fallback_text(RESULT)
    assert client.chat.completions.create.call_count == 2


def test_malformed_response_falls_back():
    client = _client(SimpleNamespace(choices=[]))
    assert explain(RESULT, client=client) == fallback_text(RESULT)


def test_missing_api_key_uses_fallback_without_calling(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    built = MagicMock()
    monkeypatch.setattr(explain_mod.openai, "OpenAI", built)
    assert explain(RESULT) == fallback_text(RESULT)
    built.assert_not_called()


def test_key_read_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = MagicMock()
    built.return_value.chat.completions.create.return_value = _reply("hi")
    monkeypatch.setattr(explain_mod.openai, "OpenAI", built)
    assert explain(RESULT) == "hi"
    assert built.call_args.kwargs["api_key"] == "sk-test"
    assert built.call_args.kwargs["max_retries"] == 0


def test_fallback_uses_only_given_numbers():
    text = fallback_text(RESULT)
    assert "0.031" in text and "0.002" in text
    assert "statistically significant" in text and "not statistically" not in text


def test_fallback_not_significant():
    result = {**RESULT, "trend": {**RESULT["trend"], "p": 0.3, "trend": "no trend"}}
    assert "not statistically significant" in fallback_text(result)


@pytest.mark.parametrize("bad", [{}, {"trend": None}, {"trend": {"slope": 1}}])
def test_fallback_handles_missing_fields(bad):
    assert "not enough trend information" in fallback_text(bad)