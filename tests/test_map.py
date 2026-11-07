"""Tests for ESD-D13-BE: the map contract and GET /map."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from earth_system_trend.api import app, thin_points
from earth_system_trend.config import get_settings
from earth_system_trend.contract import ContractError, MapPoint, load_map

ROOT = Path(__file__).parent.parent
client = TestClient(app)


def grid_map(rows: int, cols: int, step: float = 0.05) -> dict:
    points = [
        {"lat": round(33.2 + step * (r + 0.5), 4), "lon": round(-112.4 + step * (c + 0.5), 4),
         "slope": 0.01, "p": 0.2, "tau": 0.05, "trend": "no trend"}
        for r in range(rows) for c in range(cols)
    ]
    return {"region": "Test area", "variable": "LST", "units": "°C",
            "period": {"start": "2003-01", "end": "2024-12"},
            "test": "Mann-Kendall", "resolution_deg": step, "points": points}


@pytest.fixture
def map_file(tmp_path, monkeypatch):
    def write(data: dict) -> Path:
        path = tmp_path / "trend_map.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        monkeypatch.setenv("MAP_PATH", str(path))
        return path
    return write


# --- contract -------------------------------------------------------------------


def test_mock_map_matches_the_contract():
    trend_map = load_map(ROOT / "trend_map.mock.json")
    assert len(trend_map.points) == 192
    assert {p.trend for p in trend_map.points} >= {"increasing", "decreasing", "no trend", None}


def test_cell_without_data_is_all_null():
    point = MapPoint(lat=33.2, lon=-112.4, slope=None)
    assert point.p is None and point.trend is None


def test_half_filled_cell_is_rejected(tmp_path):
    data = grid_map(1, 1)
    data["points"][0]["p"] = None
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match="all be set, or all be null"):
        load_map(path)


def test_map_with_no_points_is_rejected(tmp_path):
    data = grid_map(1, 1)
    data["points"] = []
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContractError, match="map contract"):
        load_map(path)


# --- GET /map -------------------------------------------------------------------


def test_map_serves_the_mock_by_default(monkeypatch):
    monkeypatch.delenv("MAP_PATH", raising=False)
    monkeypatch.setenv("USE_MOCK", "true")
    body = client.get("/map").json()
    assert body["region"] == "Example Region"
    assert body["point_count"] == body["original_point_count"] == 192


def test_real_mode_reads_results_trend_map(monkeypatch):
    monkeypatch.delenv("MAP_PATH", raising=False)
    monkeypatch.setenv("USE_MOCK", "false")
    assert get_settings().map_path == Path("results/trend_map.json")


def test_small_map_is_sent_whole(map_file):
    map_file(grid_map(12, 16))
    body = client.get("/map").json()
    assert body["point_count"] == 192
    assert body["resolution_deg"] == 0.05


def test_big_map_is_thinned_to_5000_or_fewer(map_file):
    map_file(grid_map(100, 120))  # 12,000 cells
    body = client.get("/map").json()
    assert body["original_point_count"] == 12000
    assert 0 < body["point_count"] <= 5000
    assert body["resolution_deg"] == pytest.approx(0.1)  # every 2nd row and column


def test_max_points_lowers_the_limit(map_file):
    map_file(grid_map(12, 16))
    body = client.get("/map", params={"max_points": 50}).json()
    assert body["point_count"] <= 50
    # Thinned cells still span the whole area.
    lats = [p["lat"] for p in body["points"]]
    assert min(lats) < 33.3 and max(lats) > 33.6


def test_max_points_above_5000_is_refused(map_file):
    map_file(grid_map(2, 2))
    assert client.get("/map", params={"max_points": 9000}).status_code == 422


def test_missing_map_file_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("MAP_PATH", str(tmp_path / "nope.json"))
    response = client.get("/map")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_broken_map_file_is_500_with_reason(map_file):
    data = grid_map(1, 1)
    data["points"][0]["lat"] = 200
    map_file(data)
    response = client.get("/map")
    assert response.status_code == 500
    assert "points.0.lat" in response.json()["detail"]


def test_map_is_gzipped_when_asked(map_file):
    map_file(grid_map(12, 16))
    response = client.get("/map", headers={"Accept-Encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"


def test_tiny_answers_are_not_gzipped():
    response = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert "content-encoding" not in response.headers


def test_thin_points_keeps_everything_when_small():
    points = [MapPoint(**p) for p in grid_map(3, 3)["points"]]
    kept, step = thin_points(points, 100)
    assert kept == points and step == 1