import json

from fastapi.testclient import TestClient

from earth_system_trend.api import app

client = TestClient(app)

SAMPLE = {
    "region": "Test Region",
    "period": "2000-2020",
    "series": [{"date": "2000-01", "value": 1.0}],
    "trend": {"slope": 0.01, "p": 0.03, "tau": 0.4, "trend": "increasing"},
    "explanation": "Sample text.",
}


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_results_returns_mock_json(tmp_path, monkeypatch):
    path = tmp_path / "results.mock.json"
    path.write_text(json.dumps(SAMPLE), encoding="utf-8")
    monkeypatch.setenv("RESULTS_PATH", str(path))

    response = client.get("/results")
    assert response.status_code == 200
    assert response.json() == SAMPLE


def test_results_missing_file_is_404(tmp_path, monkeypatch):
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path / "nope.json"))
    assert client.get("/results").status_code == 404


def test_results_invalid_json_is_500(tmp_path, monkeypatch):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("RESULTS_PATH", str(path))
    assert client.get("/results").status_code == 500