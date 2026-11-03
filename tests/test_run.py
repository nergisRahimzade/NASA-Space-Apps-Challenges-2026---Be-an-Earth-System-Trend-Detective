"""Tests for ESD-D09-BE: the one-command pipeline and the USE_MOCK switch."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api import app
from earth_system_trend.config import get_settings
from earth_system_trend.contract import load_results
from earth_system_trend.explain import fallback_text
from earth_system_trend.run import PipelineError, main, run_pipeline, write_stub_series

ARGS = ("Phoenix study area", "Nighttime land surface temperature", "°C")


def test_stub_run_writes_a_valid_results_file(tmp_path):
    csv_path, out = tmp_path / "timeseries.csv", tmp_path / "out" / "results.json"
    run_pipeline(csv_path, out, *ARGS, stub=True)

    results = load_results(out)  # raises if it breaks the contract
    assert csv_path.exists()
    assert len(results.series) == 264
    assert results.period.start == "2003-01" and results.period.end == "2024-12"
    assert results.series[40].value is None
    assert results.trend.trend == "increasing"
    assert "statistically significant" in results.explanation  # fallback: no key in tests


def test_existing_csv_is_used_not_overwritten(tmp_path):
    csv_path, out = tmp_path / "timeseries.csv", tmp_path / "results.json"
    write_stub_series(csv_path, months=30)
    run_pipeline(csv_path, out, *ARGS, stub=True)
    assert len(load_results(out).series) == 30


def test_skips_when_results_are_newer_than_the_csv(tmp_path):
    csv_path, out = tmp_path / "timeseries.csv", tmp_path / "results.json"
    run_pipeline(csv_path, out, *ARGS, stub=True)
    out.write_text("left alone", encoding="utf-8")

    run_pipeline(csv_path, out, *ARGS)
    assert out.read_text(encoding="utf-8") == "left alone"

    run_pipeline(csv_path, out, *ARGS, force=True)
    assert out.read_text(encoding="utf-8") != "left alone"


def test_missing_csv_without_stub_explains_what_to_do(tmp_path):
    with pytest.raises(PipelineError, match="Run the Data steps first"):
        run_pipeline(tmp_path / "nope.csv", tmp_path / "r.json", *ARGS)


def test_too_little_data_fails_cleanly(tmp_path):
    csv_path = tmp_path / "short.csv"
    write_stub_series(csv_path, months=10)
    assert main(["--csv", str(csv_path), "--out", str(tmp_path / "r.json")]) == 1


def test_main_returns_0_on_success(tmp_path):
    out = tmp_path / "r.json"
    assert main(["--csv", str(tmp_path / "s.csv"), "--out", str(out), "--stub"]) == 0
    assert out.exists()


def test_ai_gets_the_summary_not_every_month(tmp_path, monkeypatch):
    seen = {}

    def fake_explain(result):
        seen.update(result)
        return fallback_text(result)

    monkeypatch.setattr("earth_system_trend.run.explain", fake_explain)
    run_pipeline(tmp_path / "s.csv", tmp_path / "r.json", *ARGS, stub=True)
    assert "series" not in seen
    assert seen["period"] == "2003-01 to 2024-12"


# --- USE_MOCK -------------------------------------------------------------------


def test_use_mock_defaults_to_the_mock_file(monkeypatch):
    monkeypatch.delenv("USE_MOCK", raising=False)
    monkeypatch.delenv("RESULTS_PATH", raising=False)
    assert get_settings().results_path == Path("results.mock.json")


def test_use_mock_false_serves_the_pipeline_output(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.delenv("RESULTS_PATH", raising=False)
    assert get_settings().results_path == Path("results/results.json")


def test_results_path_always_wins(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.setenv("RESULTS_PATH", "custom.json")
    assert get_settings().results_path == Path("custom.json")


def test_api_serves_what_the_pipeline_wrote(tmp_path, monkeypatch):
    out = tmp_path / "results.json"
    run_pipeline(tmp_path / "s.csv", out, *ARGS, stub=True)
    monkeypatch.setenv("RESULTS_PATH", str(out))
    body = TestClient(app).get("/results").json()
    assert body["region"] == "Phoenix study area"
    assert len(body["series"]) == 264
    json.dumps(body)  # plain JSON all the way through
