"""Tests for ESD-D14-BE: the end-to-end test (pipeline -> API -> schema checks).

The first tests run the whole chain, so CI fails if the pipeline and the API
ever stop agreeing on the contract. The rest feed the checks broken API
answers on purpose, to prove each kind of problem is caught.
"""

import copy
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from earth_system_trend import e2e
from earth_system_trend.contract import RegionsResponse, SeriesResponse, TrendResponse
from earth_system_trend.e2e import E2EError, build, in_process_api, run_checks, run_e2e

REPO = Path(__file__).resolve().parents[1]
REAL_CSV = REPO / "data" / "processed" / "timeseries.csv"
REAL_REGIONS = REPO / "docs" / "subregions.json"


# --- the whole chain ---------------------------------------------------------------


def test_e2e_with_fake_data_passes(tmp_path):
    report = run_e2e(tmp_path, stub=True)
    assert report.failed == []
    # health, results, regions, default trend, 404 + (series, trend) per region
    assert len(report.passed) == 5 + 2 * (1 + len(e2e.STUB_REGIONS))


@pytest.mark.skipif(not REAL_CSV.exists(), reason="the Data layer's CSVs are not in this checkout")
def test_e2e_with_the_committed_data_passes(tmp_path):
    report = run_e2e(tmp_path, csv=REAL_CSV, regions_file=REAL_REGIONS)
    assert report.failed == []


def test_e2e_never_touches_the_real_results_folder(tmp_path):
    before = sorted(p.stat().st_mtime for p in (REPO / "results").rglob("*.json"))
    run_e2e(tmp_path, stub=True)
    assert sorted(p.stat().st_mtime for p in (REPO / "results").rglob("*.json")) == before
    assert (tmp_path / "results" / "results.json").exists()


def test_e2e_restores_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", "original.json")
    monkeypatch.delenv("REGIONS_DIR", raising=False)
    run_e2e(tmp_path, stub=True)
    assert os.environ["RESULTS_PATH"] == "original.json"
    assert "REGIONS_DIR" not in os.environ


def test_missing_csv_is_a_setup_error(tmp_path):
    with pytest.raises(E2EError, match="not found"):
        run_e2e(tmp_path, csv=tmp_path / "nope.csv", regions_file=REAL_REGIONS)


def test_main_exit_codes(tmp_path):
    assert e2e.main(["--stub", "--keep", str(tmp_path / "ok")]) == 0
    assert e2e.main(["--csv", str(tmp_path / "nope.csv")]) == 1


# --- the checks catch broken answers -------------------------------------------------


@pytest.fixture
def built(tmp_path):
    """Pipeline output in tmp_path, with the env pointed at it for in-process API calls."""
    csv, regions_file = e2e.write_stub_inputs(tmp_path / "inputs")
    placeholder = e2e.Built(tmp_path / "results" / "results.json", tmp_path / "results" / "regions", [])
    with e2e.api_env(placeholder, tmp_path / "cache.json", with_ai=False):
        yield build(tmp_path, csv, regions_file)


def run_with(built, tamper):
    """Run the checks with tamper(path, params, status, body) rewriting each API answer."""
    with in_process_api() as real_get:
        def get(path, params=None):
            status, body = real_get(path, params)
            return tamper(path, params, status, copy.deepcopy(body))
        return run_checks(get, built)


def failed_names(report):
    return [name for name, _ in report.failed]


def test_untouched_answers_pass(built):
    assert run_with(built, lambda path, params, status, body: (status, body)).failed == []


def test_extra_field_is_caught(built):
    def tamper(path, params, status, body):
        if path == "/results":
            body["surprise"] = 1
        return status, body
    assert failed_names(run_with(built, tamper)) == [
        "/results matches the contract and the pipeline output"]


def test_renamed_trend_field_is_caught(built):
    def tamper(path, params, status, body):
        if path == "/trend" and params and status == 200:
            body["trend"]["slpoe"] = body["trend"].pop("slope")
        return status, body
    failed = failed_names(run_with(built, tamper))
    assert failed and all(name.startswith("/trend?region=") for name in failed)


def test_api_serving_different_numbers_is_caught(built):
    def tamper(path, params, status, body):
        if path == "/regions":
            body["regions"][1]["trend"]["slope"] += 1
        return status, body
    report = run_with(built, tamper)
    assert failed_names(report) == ["/regions lists the study area and every sub-region"]
    assert "differs from the pipeline's file" in report.failed[0][1]


def test_gap_in_series_is_caught(built):
    def tamper(path, params, status, body):
        if path == "/series" and params == {"region": "stub_north"}:
            del body["series"][10]
        return status, body
    report = run_with(built, tamper)
    assert failed_names(report) == ["/series?region=stub_north"]


def test_missing_region_is_caught(built):
    def tamper(path, params, status, body):
        if path == "/regions":
            body["regions"] = body["regions"][:-1]
        return status, body
    assert "/regions lists the study area and every sub-region" in failed_names(run_with(built, tamper))


def test_server_error_is_caught(built):
    def tamper(path, params, status, body):
        return (500, {"detail": "boom"}) if path == "/health" else (status, body)
    report = run_with(built, tamper)
    assert failed_names(report) == ["/health is ok"]
    assert "HTTP 500" in report.failed[0][1]


def test_unknown_region_must_be_404(built):
    def tamper(path, params, status, body):
        if params == {"region": e2e.UNKNOWN_REGION}:
            return 200, {}
        return status, body
    assert failed_names(run_with(built, tamper)) == ["unknown region answers 404 with a message"]


def test_trend_label_that_disagrees_with_p_is_caught(built):
    results = json.loads(built.results_path.read_text(encoding="utf-8"))
    results["trend"].update(p=0.5, trend="increasing", tau=0.2)
    built.results_path.write_text(json.dumps(results), encoding="utf-8")
    report = run_with(built, lambda path, params, status, body: (status, body))
    assert "p=0.5 but trend is 'increasing'" in " ".join(msg for _, msg in report.failed)


# --- the response models -------------------------------------------------------------


def test_response_models_reject_unknown_fields():
    period = {"start": "2003-01", "end": "2003-02"}
    trend = {"slope": 0.1, "p": 0.01, "tau": 0.5, "trend": "increasing"}
    base = {"region": "R", "variable": "V", "units": "°C", "period": period}
    TrendResponse.model_validate({**base, "trend": trend, "explanation": None})
    SeriesResponse.model_validate({**base, "series": [{"date": "2003-01", "value": None}]})
    with pytest.raises(ValidationError):
        TrendResponse.model_validate({**base, "trend": trend, "explanation": None, "x": 1})
    with pytest.raises(ValidationError):
        RegionsResponse.model_validate({"regions": []})  # at least the study area