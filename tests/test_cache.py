"""Tests for ESD-D04-BE: the file-based explanation cache."""

from earth_system_trend.cache import cache_get, cache_put, make_key


def test_key_ignores_dictionary_order():
    assert make_key({"a": 1, "b": 2}) == make_key({"b": 2, "a": 1})


def test_different_input_gives_different_key():
    assert make_key({"a": 1}) != make_key({"a": 2})


def test_put_then_get(tmp_path):
    path = tmp_path / "nested" / "cache.json"
    assert cache_get(path, "k") is None
    cache_put(path, "k", "saved answer")
    assert cache_get(path, "k") == "saved answer"


def test_damaged_cache_acts_empty(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("{not json", encoding="utf-8")
    assert cache_get(path, "k") is None
    cache_put(path, "k", "v")
    assert cache_get(path, "k") == "v"


def test_cache_that_is_not_a_dictionary_acts_empty(tmp_path):
    path = tmp_path / "cache.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert cache_get(path, "k") is None


def test_unwritable_cache_does_not_raise(tmp_path):
    cache_put(tmp_path, "k", "v")  # a folder, not a file: the write fails quietly
    assert cache_get(tmp_path, "k") is None
