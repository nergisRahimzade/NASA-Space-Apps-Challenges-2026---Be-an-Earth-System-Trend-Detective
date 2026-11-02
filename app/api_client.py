import json
import os
from pathlib import Path

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")
MOCK_FILE = Path(__file__).resolve().parent.parent / "results.mock.json"


def load_results():
    """Return (results, source). Try the API first, then the local mock file."""
    try:
        response = requests.get(f"{API_URL}/results", timeout=3)
        response.raise_for_status()
        return response.json(), f"API at {API_URL}"
    except requests.RequestException:
        with open(MOCK_FILE, encoding="utf-8") as f:
            return json.load(f), "local results.mock.json"


def load_series(region, variable):
    """Fetch one series from GET /series and return the parsed JSON.

    Raises requests.RequestException if the API can't be reached or answers
    with an error. There is no local fallback: only the default selection
    exists in results.mock.json.
    """
    response = requests.get(
        f"{API_URL}/series",
        params={"region": region, "variable": variable},
        timeout=3,
    )
    response.raise_for_status()
    return response.json()