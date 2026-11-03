"""Tests for ESD-D07-BE: CORS headers and the rate limit."""

import pytest
from fastapi.testclient import TestClient

from earth_system_trend import api
from earth_system_trend.config import get_settings
from earth_system_trend.rate_limit import RateLimiter

client = TestClient(api.app)


@pytest.fixture
def limit_of_3(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    api.rate_limiter.reset()
    yield
    api.rate_limiter.reset()


# --- CORS ---------------------------------------------------------------


def test_allowed_origin_gets_cors_header():
    response = client.get("/health", headers={"Origin": "http://localhost:8501"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:8501"


def test_unknown_origin_gets_no_cors_header():
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_setting_is_a_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://a.example, https://b.example")
    assert get_settings().cors_origins == ["http://a.example", "https://b.example"]


# --- rate limit through the API -------------------------------------------


def test_fourth_request_in_a_minute_is_blocked(limit_of_3):
    codes = [client.get("/results").status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_blocked_answer_explains_itself(limit_of_3):
    for _ in range(3):
        client.get("/results")
    response = client.get("/results")
    assert "Too many requests" in response.json()["detail"]
    assert response.headers["retry-after"] == "60"


def test_health_is_never_limited(limit_of_3):
    assert all(client.get("/health").status_code == 200 for _ in range(10))


def test_limit_of_zero_turns_it_off():
    assert all(client.get("/results").status_code == 200 for _ in range(100))


# --- the limiter on its own, with a fake clock ----------------------------


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_window_slides_forward():
    clock = FakeClock()
    limiter = RateLimiter(window_s=60, clock=clock)
    assert limiter.allow("ip", 2) and limiter.allow("ip", 2)
    assert not limiter.allow("ip", 2)
    clock.now = 61  # a minute later the old requests no longer count
    assert limiter.allow("ip", 2)


def test_each_visitor_has_their_own_count():
    limiter = RateLimiter()
    assert limiter.allow("a", 1)
    assert not limiter.allow("a", 1)
    assert limiter.allow("b", 1)
