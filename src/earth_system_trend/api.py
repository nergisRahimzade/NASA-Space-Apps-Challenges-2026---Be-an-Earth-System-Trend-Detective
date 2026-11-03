"""The backend API: serves analysis results to the dashboard.

Run it with:  uv run --locked uvicorn earth_system_trend.api:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import configure_logging, get_settings
from .contract import ContractError, Results, load_results
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
    """The whole results file, checked against the contract first (ESD-D10-BE)."""
    return load_current_results().model_dump()


def load_current_results() -> Results:
    """Load the results file the settings point at, checked against the contract.

    Answers 404 if the file is missing and 500 if it is broken, with a message
    that says what is wrong.
    """
    path = results_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Results file not found: {path}")
    try:
        return load_results(path)
    except ContractError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _same(a: str, b: str) -> bool:
    return a.strip().casefold() == b.strip().casefold()


@app.get("/series")
def get_series(region: str, variable: str | None = None) -> dict:
    """ESD-D08-BE. One monthly series, for the time-series chart.

    Example: /series?region=Phoenix%20study%20area&variable=...
    `variable` is optional. Answers 404 if there is no data for that choice.
    """
    results = load_current_results()
    if not _same(region, results.region) or (variable and not _same(variable, results.variable)):
        wanted = region if not variable else f"{region} / {variable}"
        raise HTTPException(status_code=404, detail=f"No series for {wanted}")
    return {
        "region": results.region,
        "variable": results.variable,
        "units": results.units,
        "period": results.period.model_dump(),
        "series": [point.model_dump() for point in results.series],
    }


@app.get("/trend")
def get_trend() -> dict:
    """ESD-D10-BE. The trend numbers and explanation, for the stat cards and AI box.

    Same checks as /results: 404 if the file is missing, 500 if it breaks the contract.
    """
    results = load_current_results()
    return {
        "region": results.region,
        "variable": results.variable,
        "units": results.units,
        "period": results.period.model_dump(),
        "trend": results.trend.model_dump(),
        "explanation": results.explanation,
    }
