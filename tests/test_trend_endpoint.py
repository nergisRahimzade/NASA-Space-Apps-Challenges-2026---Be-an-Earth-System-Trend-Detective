"""Tests for ESD-D10-BE: GET /trend, and /results now checked against the contract."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api import app

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


@pytest.fixture
def results_file(tmp_path, monkeypatch):
    path = tmp_path / "results.json"
    path.write_text((FIXTURES / "valid_results.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("RESULTS_PATH", str(path))
    return path


def break_it(path, change):
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_trend_returns_the_numbers(results_file):
    response = client.get("/trend")
    assert response.status_code == 200
    body = response.json()
    assert body["trend"] == {"slope": 0.02, "p": 0.03, "tau": 0.21, "trend": "increasing"}
    assert body["units"] == "°C"
    assert body["period"] == {"start": "2000-01", "end": "2000-03"}
    assert "series" not in body  # the stat cards don't need every month


def test_trend_works_on_the_default_mock_file():
    body = client.get("/trend").json()
    assert body["trend"]["trend"] == "increasing"
    assert body["explanation"].startswith("The series shows")


def test_trend_missing_file_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path / "nope.json"))
    assert client.get("/trend").status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["trend"].update(trend="up"),  # not one of the three allowed words
        lambda d: d["trend"].update(tau=2),  # tau must be between -1 and 1
        lambda d: d.pop("units"),  # every field is required
        lambda d: d.update(slpoe=1),  # unknown keys are rejected
    ],
)
@pytest.mark.parametrize("path", ["/trend", "/results"])
def test_results_that_break_the_contract_give_500(results_file, change, path):
    break_it(results_file, change)
    response = client.get(path)
    assert response.status_code == 500
    assert "contract" in response.json()["detail"]
