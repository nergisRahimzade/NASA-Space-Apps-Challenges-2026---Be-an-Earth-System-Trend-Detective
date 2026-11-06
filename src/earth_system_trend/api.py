"""The backend API: serves analysis results to the dashboard.

Run it with:  uv run --locked uvicorn earth_system_trend.api:app --reload
"""
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from .config import configure_logging, get_settings
from .contract import ContractError, MapPoint, Results, load_map, load_results
from .rate_limit import RateLimiter
from .regions import RegionResults, load_region_files, matches, slugify

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
# ESD-D13-BE. Compress any answer bigger than 1 kB when the browser accepts gzip
# (every browser and the requests library do). JSON shrinks to a fraction of
# its size, so the map and the 264-month series load faster.
app.add_middleware(GZipMiddleware, minimum_size=1000)

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
    """Load the results file and check it against the contract.

    Which file: results_path() asks config.py. By default (USE_MOCK=true) it is
    results.mock.json; with USE_MOCK=false it is results/results.json, written
    by the pipeline (python -m earth_system_trend.run); RESULTS_PATH overrides both.

    Answers 404 if the file is missing and 500 if it breaks the contract, with a
    message that says what is wrong. /results, /series and /trend all use this.
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


def all_regions() -> list[RegionResults]:
    """ESD-D12-BE. The whole study area first, then each sub-region file."""
    main = load_current_results()
    return [RegionResults(id=slugify(main.region), results=main),
            *load_region_files(get_settings().regions_dir)]


def find_region(region: str) -> Results:
    """The results for one region, found by its id or label. 404 if there is none."""
    for entry in all_regions():
        if matches(entry, region):
            return entry.results
    raise HTTPException(status_code=404, detail=f"No data for region: {region}")


@app.get("/regions")
def get_regions() -> dict:
    """ESD-D12-BE. Every region with data and its trend, for the dropdown and compare chart.

    The whole study area comes first. Use a region's `id` (or its label) in
    /series?region=... and /trend?region=...
    """
    return {
        "regions": [
            {
                "id": entry.id,
                "region": entry.results.region,
                "variable": entry.results.variable,
                "units": entry.results.units,
                "period": entry.results.period.model_dump(),
                "trend": entry.results.trend.model_dump(),
            }
            for entry in all_regions()
        ]
    }


@app.get("/series")
def get_series(region: str, variable: str | None = None) -> dict:
    """ESD-D08-BE. One monthly series, for the time-series chart.

    Example: /series?region=phoenix_northwest&variable=...
    `region` is a region's id or label (see /regions); `variable` is optional.
    Answers 404 if there is no data for that choice.
    """
    results = find_region(region)
    if variable and not _same(variable, results.variable):
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
def get_trend(region: str | None = None) -> dict:
    """ESD-D10-BE. The trend numbers and explanation, for the stat cards and AI box.

    Same checks as /results: 404 if the file is missing, 500 if it breaks the contract.
    ESD-D12-BE: add ?region=<id or label> for a sub-region (see /regions).
    """
    # `results` is the whole results file, read and checked by load_current_results()
    # above (results.mock.json by default, results/results.json with USE_MOCK=false),
    # or one sub-region's file when ?region= is given.
    results = find_region(region) if region else load_current_results()
    return {
        "region": results.region,
        "variable": results.variable,
        "units": results.units,
        "period": results.period.model_dump(),
        "trend": results.trend.model_dump(),
        "explanation": results.explanation,
    }
# --- ESD-D13-BE: the trend map ------------------------------------------------
MAX_MAP_POINTS = 5000  # the most cells /map ever sends; keeps the page fast


def thin_points(points: list[MapPoint], max_points: int) -> tuple[list[MapPoint], int]:
    """Keep at most max_points cells, spread evenly over the grid.

    Returns (kept points, step). With step k, every k-th row and every k-th
    column of the grid is kept, so the map still covers the whole area, just
    with bigger cells. step is 1 when nothing had to be dropped.
    """
    if len(points) <= max_points:
        return points, 1
    lats = {lat: i for i, lat in enumerate(sorted({p.lat for p in points}))}
    lons = {lon: i for i, lon in enumerate(sorted({p.lon for p in points}))}
    step = math.ceil(math.sqrt(len(points) / max_points))
    while True:
        kept = [p for p in points if lats[p.lat] % step == 0 and lons[p.lon] % step == 0]
        if len(kept) <= max_points:
            return kept, step
        step += 1  # an irregular grid can need a bigger step


@app.get("/map")
def get_map(
    max_points: int = Query(MAX_MAP_POINTS, ge=1, le=MAX_MAP_POINTS,
                            description="Most cells to return (1 to 5000)"),
) -> dict:
    """ESD-D13-BE. Per-cell trends for the trend map.

    Reads trend_map.mock.json by default, results/trend_map.json with
    USE_MOCK=false, or MAP_PATH. Answers 404 if the file is missing and 500 if
    it breaks the map contract (docs/contract.md). Large grids are thinned to
    max_points cells; `resolution_deg` then grows to match, so the cells still
    tile the area.
    """
    path = get_settings().map_path
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Map file not found: {path}")
    try:
        trend_map = load_map(path)
    except ContractError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    points, step = thin_points(trend_map.points, max_points)
    body = trend_map.model_dump()
    body["resolution_deg"] = round(trend_map.resolution_deg * step, 6)
    body["points"] = [point.model_dump() for point in points]
    body["point_count"] = len(points)
    body["original_point_count"] = len(trend_map.points)
    return body