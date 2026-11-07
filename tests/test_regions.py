"""Tests for ESD-D12-BE: /regions, ?region= on /series and /trend, and --all-regions."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api import app
from earth_system_trend.config import get_settings
from earth_system_trend.contract import load_results
from earth_system_trend.regions import slugify
from earth_system_trend.run import (
    PipelineError,
    load_region_list,
    main,
    run_all_regions,
)

FIXTURES = Path(__file__).parent / "fixtures"
client = TestClient(app)


def write_results(path: Path, region: str, slope: float = 0.02) -> None:
    data = json.loads((FIXTURES / "valid_results.json").read_text(encoding="utf-8"))
    data["region"] = region
    data["trend"]["slope"] = slope
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def two_regions(tmp_path, monkeypatch):
    """A main results file plus two sub-region files."""
    main_file = tmp_path / "results.json"
    write_results(main_file, "Phoenix study area", slope=0.01)
    regions = tmp_path / "regions"
    write_results(regions / "phoenix_northwest.json", "Phoenix northwest window", slope=0.03)
    write_results(regions / "phoenix_southeast.json", "Phoenix southeast window", slope=-0.02)
    monkeypatch.setenv("RESULTS_PATH", str(main_file))
    monkeypatch.setenv("REGIONS_DIR", str(regions))
    return regions


# --- /regions -------------------------------------------------------------------


def test_regions_lists_study_area_first_then_sub_regions(two_regions):
    body = client.get("/regions").json()
    assert [r["id"] for r in body["regions"]] == [
        "phoenix_study_area", "phoenix_northwest", "phoenix_southeast"]
    assert body["regions"][1]["region"] == "Phoenix northwest window"
    assert body["regions"][2]["trend"]["slope"] == -0.02
    assert "series" not in body["regions"][0]  # the list stays small


def test_regions_in_mock_mode_is_just_the_mock_region(monkeypatch):
    monkeypatch.delenv("REGIONS_DIR", raising=False)
    monkeypatch.delenv("RESULTS_PATH", raising=False)
    monkeypatch.setenv("USE_MOCK", "true")
    body = client.get("/regions").json()
    assert [r["region"] for r in body["regions"]] == ["Example Region"]


def test_real_mode_reads_results_regions_by_default(monkeypatch):
    monkeypatch.delenv("REGIONS_DIR", raising=False)
    monkeypatch.setenv("USE_MOCK", "false")
    assert get_settings().regions_dir == Path("results/regions")


def test_bad_region_file_is_skipped_not_fatal(two_regions):
    (two_regions / "broken.json").write_text("{not json", encoding="utf-8")
    ids = [r["id"] for r in client.get("/regions").json()["regions"]]
    assert "broken" not in ids and len(ids) == 3


def test_missing_regions_folder_means_no_sub_regions(tmp_path, monkeypatch, two_regions):
    monkeypatch.setenv("REGIONS_DIR", str(tmp_path / "nope"))
    assert len(client.get("/regions").json()["regions"]) == 1


# --- ?region= on /series and /trend -------------------------------------------


@pytest.mark.parametrize("name", ["phoenix_northwest", "Phoenix northwest window", "PHOENIX_NORTHWEST"])
def test_series_finds_a_sub_region_by_id_or_label(two_regions, name):
    response = client.get("/series", params={"region": name})
    assert response.status_code == 200
    assert response.json()["region"] == "Phoenix northwest window"


def test_series_still_finds_the_study_area(two_regions):
    assert client.get("/series", params={"region": "Phoenix study area"}).status_code == 200


def test_trend_for_a_sub_region(two_regions):
    body = client.get("/trend", params={"region": "phoenix_southeast"}).json()
    assert body["trend"]["slope"] == -0.02


def test_trend_without_region_is_the_study_area(two_regions):
    assert client.get("/trend").json()["region"] == "Phoenix study area"


def test_unknown_region_is_404(two_regions):
    for path in ("/series", "/trend"):
        response = client.get(path, params={"region": "Mars"})
        assert response.status_code == 404
        assert "Mars" in response.json()["detail"]


def test_slugify():
    assert slugify("Phoenix study area") == "phoenix_study_area"
    assert slugify("  Los Angeles / Long Beach ") == "los_angeles_long_beach"


# --- --all-regions -----------------------------------------------------------------


def write_region_list(path: Path, ids: list[str]) -> None:
    regions = {i: {"label": i.replace("_", " ").title(), "bounds": [0, 0, 1, 1]} for i in ids}
    path.write_text(json.dumps({"regions": regions}), encoding="utf-8")


def test_all_regions_writes_one_valid_file_per_region(tmp_path):
    regions_file = tmp_path / "subregions.json"
    write_region_list(regions_file, ["phoenix_northwest", "phoenix_southeast"])
    paths = run_all_regions(regions_file, tmp_path / "csv", tmp_path / "out",
                            "Nighttime LST", "°C", stub=True)
    assert sorted(p.name for p in paths) == ["phoenix_northwest.json", "phoenix_southeast.json"]
    assert load_results(tmp_path / "out" / "phoenix_northwest.json").region == "Phoenix Northwest"
    assert (tmp_path / "csv" / "timeseries_phoenix_southeast.csv").exists()


def test_all_regions_reports_every_failure_together(tmp_path):
    regions_file = tmp_path / "subregions.json"
    write_region_list(regions_file, ["a", "b"])
    with pytest.raises(PipelineError, match="2 region"):
        run_all_regions(regions_file, tmp_path / "csv", tmp_path / "out", "V", "U")


def test_missing_or_bad_region_list_is_explained(tmp_path):
    with pytest.raises(PipelineError, match="not found"):
        load_region_list(tmp_path / "nope.json")
    bad = tmp_path / "bad.json"
    bad.write_text('{"zones": []}', encoding="utf-8")
    with pytest.raises(PipelineError, match="must look like"):
        load_region_list(bad)


def test_all_regions_from_the_command_line(tmp_path):
    regions_file = tmp_path / "subregions.json"
    write_region_list(regions_file, ["phoenix_northwest"])
    code = main(["--all-regions", "--stub", "--regions-file", str(regions_file),
                 "--csv", str(tmp_path / "csv" / "timeseries.csv"),
                 "--regions-out", str(tmp_path / "out")])
    assert code == 0
    assert (tmp_path / "out" / "phoenix_northwest.json").exists()
