"""Day 2 API: serves the mock results so FE can build against it."""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException

from .config import configure_logging, get_settings

configure_logging()

app = FastAPI(title="Earth System Trend Detective API")


def results_path() -> Path:
    # Read per request so tests (and later USE_MOCK switching) can change it.
    return get_settings().results_path


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
