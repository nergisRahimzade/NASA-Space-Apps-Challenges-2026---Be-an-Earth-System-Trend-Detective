"""Day 2 API: serves the mock results so FE can build against it."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

DEFAULT_RESULTS_PATH = "results.mock.json"

app = FastAPI(title="Earth System Trend Detective API")


def results_path() -> Path:
    # Read per request so tests (and later USE_MOCK switching) can change it.
    return Path(os.environ.get("RESULTS_PATH", DEFAULT_RESULTS_PATH))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/results")
def get_results() -> dict:
    path = results_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Results file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Results file is not valid JSON: {exc}")