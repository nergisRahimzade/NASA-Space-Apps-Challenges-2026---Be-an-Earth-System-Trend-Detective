"""Shared test setup. pytest loads this file automatically."""

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Runs before every test.

    - Removes any real OpenAI key, so no test can call the real API.
    - Points the explanation cache at a fresh temp file, so one test's
      cached answer can never leak into another test.
    """
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("EXPLAIN_CACHE_PATH", str(tmp_path / "explain_cache.json"))
