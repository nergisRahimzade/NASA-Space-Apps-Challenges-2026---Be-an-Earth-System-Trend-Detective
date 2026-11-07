import json
import os
from pathlib import Path

import requests

# A trailing slash (http://localhost:8000/) is fine: it is removed here.
API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
MOCK_FILE = Path(__file__).resolve().parent.parent / "results.mock.json"

# ---------------------------------------------------------------------------
# WHAT THE BACKEND TEAM CONFIRMED (Nov 2026)
#   GET /series?region=...&variable=...
#     region is required (422 if missing). variable is optional and defaults to
#     the main variable. Matching ignores upper/lower case.
#     No data for a region/variable -> 404 {"detail": "No series for ..."}
#     Answer: {region, variable, units, period{start,end}, series[{date,value}]}
#     Dates are "YYYY-MM". A value may be null (missing month).
#   GET /regions  returns the region list (real list from Day 12). Its exact
#     shape is NOT confirmed yet, so parse_regions() accepts a few shapes.
# If any of this changes, edit this section, parse_series() and parse_regions().
# ---------------------------------------------------------------------------
SERIES_PATH = "/series"
REGIONS_PATH = "/regions"
REGION_PARAM = "region"
VARIABLE_PARAM = "variable"
SEND_VARIABLE = True

# Used only if GET /regions is unavailable.
FALLBACK_REGIONS = ["Example Region B", "Example Region C"]
# Only the main variable has data until Day 15. Add the second one then.
EXTRA_VARIABLES = []


class NoSeriesError(ValueError):
    """The API has no series for this region/variable (HTTP 404)."""


def parse_regions(data):
    """Turn the /regions answer into a list of names.

    Accepts a list of names, a list of {"name": ...} or {"region": ...}
    objects, or {"regions": [...]}.
    """
    if isinstance(data, dict):
        data = data.get("regions", [])
    if not isinstance(data, list):
        return []
    names = []
    for item in data:
        if isinstance(item, str):
            names.append(item)
        elif isinstance(item, dict):
            name = item.get("name") or item.get("region")
            if name:
                names.append(name)
    return names


def load_regions():
    """Region names from GET /regions, or None if the endpoint isn't available."""
    try:
        response = requests.get(f"{API_URL}{REGIONS_PATH}", timeout=3)
        response.raise_for_status()
        names = parse_regions(response.json())
    except (requests.RequestException, ValueError):
        return None
    return names or None


def load_choices(default_region, default_variable):
    """Return (region_choices, variable_choices) for the dropdowns.

    The default region and variable always come first.
    """
    regions = load_regions()
    if regions is None:
        regions = list(FALLBACK_REGIONS)
    regions = [default_region] + [r for r in regions if r != default_region]
    return regions, [default_variable, *EXTRA_VARIABLES]


def parse_series(data, region, variable, default_units):
    """Turn the API's /series answer into the dict the chart expects.

    This is the one place that knows the response's key names. If the answer
    is wrapped, for example {"data": {...}}, unwrap it first: data = data["data"]
    """
    points = data["series"]
    dates = [pt["date"] for pt in points]
    period = data.get("period", {})
    return {
        "region": data.get("region", region),
        "variable": data.get("variable", variable),
        "units": data.get("units", default_units),
        "start": period.get("start", dates[0] if dates else ""),
        "end": period.get("end", dates[-1] if dates else ""),
        "dates": dates,
        "values": [pt["value"] for pt in points],  # value may be null (missing)
        # No trend statistics exist for a chosen series yet, so no trend line.
        "slope": None,
        "intercept": None,
    }


def _error_detail(response):
    """The API's explanation of an error, from {"detail": ...}."""
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        return response.text[:200] or f"HTTP {response.status_code}"
    if isinstance(detail, list):  # validation errors (422) come as a list
        return "; ".join(
            str(d.get("msg", d)) if isinstance(d, dict) else str(d) for d in detail
        )
    return str(detail) if detail else f"HTTP {response.status_code}"


def load_results():
    """Return (results, source). Try the API first, then the local mock file."""
    try:
        response = requests.get(f"{API_URL}/results", timeout=3)
        response.raise_for_status()
        return response.json(), f"API at {API_URL}"
    except requests.RequestException as exc:
        with open(MOCK_FILE, encoding="utf-8") as f:
            reason = type(exc).__name__
            source = f"local results.mock.json (API at {API_URL} not used: {reason})"
            return json.load(f), source
        
def load_series(region, variable, default_units="[unit]"):
    """Fetch one series and return it in the shape the chart expects.

    Raises NoSeriesError for a 404 (no data), ValueError for a 422, and
    requests.RequestException if the API can't be reached. There is no local
    fallback: only the default selection exists in results.mock.json.
    """
    params = {REGION_PARAM: region}
    if SEND_VARIABLE:
        params[VARIABLE_PARAM] = variable
    response = requests.get(f"{API_URL}{SERIES_PATH}", params=params, timeout=3)
    if response.status_code == 404:
        raise NoSeriesError(_error_detail(response))
    if response.status_code == 422:
        raise ValueError(_error_detail(response))
    response.raise_for_status()
    return parse_series(response.json(), region, variable, default_units)