"""Tests for ESD-D08-BE: load_timeseries() and GET /series."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api import app
from earth_system_trend.timeseries import TimeseriesError, load_timeseries, next_month

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


# --- load_timeseries ---------------------------------------------------------


def test_reads_the_mock_csv_and_fills_gaps():
    series = load_timeseries(FIXTURES / "timeseries_mock.csv")
    assert [(p.date, p.value) for p in series] == [
        ("2003-01", 13.2),
        ("2003-02", None),  # empty value
        ("2003-03", None),  # month left out of the file
        ("2003-04", 17.5),
        ("2003-05", None),  # NaN
        ("2003-06", 21.0),  # full date cut to its month
    ]


def test_rows_in_any_order_come_out_sorted(tmp_path):
    path = tmp_path / "s.csv"
    path.write_text("date,value\n2003-02,2\n2003-01,1\n", encoding="utf-8")
    assert [p.date for p in load_timeseries(path)] == ["2003-01", "2003-02"]


def test_next_month_rolls_over_the_year():
    assert next_month("2003-12") == "2004-01"
    assert next_month("2003-09") == "2003-10"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("month,temp\n2003-01,1\n", "needs 'date' and 'value'"),
        ("date,value\n", "no rows"),
        ("date,value\n2003-13,1\n", "bad date"),
        ("date,value\n2003-01,warm\n", "bad value"),
        ("date,value\n2003-01,1\n2003-01,2\n", "appears twice"),
    ],
)
def test_bad_csv_is_rejected_clearly(tmp_path, content, message):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(TimeseriesError, match=message):
        load_timeseries(path)


def test_missing_csv_is_rejected(tmp_path):
    with pytest.raises(TimeseriesError, match="not found"):
        load_timeseries(tmp_path / "nope.csv")


# --- GET /series ----------------------------------------------------------------


@pytest.fixture
def results_file(tmp_path, monkeypatch):
    path = tmp_path / "results.json"
    path.write_text((FIXTURES / "valid_results.json").read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("RESULTS_PATH", str(path))
    return path


def test_series_for_the_results_region(results_file):
    response = client.get("/series", params={"region": "Test Region"})
    assert response.status_code == 200
    body = response.json()
    assert body["units"] == "°C"
    assert body["period"] == {"start": "2000-01", "end": "2000-03"}
    assert [p["value"] for p in body["series"]] == [1.2, None, 1.5]


def test_region_and_variable_match_ignoring_case(results_file):
    params = {"region": "test region", "variable": "SURFACE AIR TEMPERATURE"}
    assert client.get("/series", params=params).status_code == 200


def test_unknown_region_is_404(results_file):
    response = client.get("/series", params={"region": "Mars"})
    assert response.status_code == 404
    assert "Mars" in response.json()["detail"]


def test_unknown_variable_is_404(results_file):
    params = {"region": "Test Region", "variable": "Rainfall"}
    assert client.get("/series", params=params).status_code == 404


def test_region_is_required():
    assert client.get("/series").status_code == 422


def test_results_that_break_the_contract_give_500(results_file):
    data = json.loads(results_file.read_text(encoding="utf-8"))
    data["trend"]["trend"] = "up"
    results_file.write_text(json.dumps(data), encoding="utf-8")
    response = client.get("/series", params={"region": "Test Region"})
    assert response.status_code == 500
    assert "contract" in response.json()["detail"]


def test_default_mock_region_works():
    # With no settings, the API serves results.mock.json, whose region is "Example Region".
    assert client.get("/series", params={"region": "Example Region"}).status_code == 200
