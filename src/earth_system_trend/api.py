"""The backend API: serves analysis results to the dashboard.

Run it with:  uv run --locked uvicorn earth_system_trend.api:app --reload
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import configure_logging, get_settings
from .rate_limit import RateLimiter

configure_logging()

app = FastAPI(title="Earth System Trend Detective API")

# ESD-D07-BE. CORS: a browser only lets a web page read answers from another
# address (here, the API) if the API lists that page's address as allowed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ESD-D07-BE. A simple rate limit: each visitor gets a fixed number of
# requests per minute. /health is exempt so uptime checks never get blocked.
rate_limiter = RateLimiter(window_s=60.0)


@app.middleware("http")
async def limit_requests(request: Request, call_next):
    limit = get_settings().rate_limit_per_minute
    client = request.client.host if request.client else "unknown"
    if request.url.path != "/health" and not rate_limiter.allow(client, limit):
        return JSONResponse(
            status_code=429,
            content={"detail": f"Too many requests: the limit is {limit} per minute."},
            headers={"Retry-After": "60"},
        )
    return await call_next(request)


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
