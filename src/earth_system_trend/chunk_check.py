"""Check Dask chunks and time a small per-cell trial for ESD-D12-DAT."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

import dask
import numpy as np
import pymannkendall
import xarray as xr

from .contract import SeriesPoint
from .trend import MIN_VALUES, TrendError, run_trend

REQUESTED_CHUNKS = {"time": -1, "lat": 50, "lon": 50}


def chunk_nighttime(dataset: xr.Dataset) -> xr.DataArray:
    data = dataset["lst_night"]
    if set(data.dims) != {"time", "lat", "lon"}:
        raise ValueError("Nighttime LST must have time, lat and lon dimensions.")
    if data.attrs.get("units") != "degC":
        raise ValueError("Expected nighttime LST units of degC.")
    months = np.asarray(data.time.values, dtype="datetime64[M]")
    if len(months) < MIN_VALUES or np.isnat(months).any():
        raise ValueError(f"Need at least {MIN_VALUES} dated months.")
    expected = np.arange(months[0], months[-1] + np.timedelta64(1, "M"), dtype="datetime64[M]")
    if not np.array_equal(months, expected):
        raise ValueError("Monthly dates must be sorted, unique and complete.")
    if not data.sizes["lat"] or not data.sizes["lon"]:
        raise ValueError("The spatial window is empty.")
    return data.transpose("time", "lat", "lon").chunk(REQUESTED_CHUNKS)


def benchmark_cells(data: xr.DataArray, box_size: int = 4, budget_seconds: float = 30.0) -> dict:
    if box_size < 1 or box_size > min(data.sizes["lat"], data.sizes["lon"]):
        raise ValueError("The sample box must fit inside the spatial window.")
    if not np.isfinite(budget_seconds) or budget_seconds <= 0:
        raise ValueError("The time budget must be positive and finite.")
    row = (data.sizes["lat"] - box_size) // 2
    col = (data.sizes["lon"] - box_size) // 2
    sample = data.isel(lat=slice(row, row + box_size), lon=slice(col, col + box_size))
    start = perf_counter()
    loaded = sample.compute(scheduler="single-threaded")
    load_seconds = perf_counter() - start
    dates = np.asarray(loaded.time.values, dtype="datetime64[M]").astype(str).tolist()
    tested = incomplete = failed = 0
    start = perf_counter()
    for i in range(box_size):
        for j in range(box_size):
            values = loaded.values[:, i, j]
            # The current backend removes missing months before fitting. Do not
            # benchmark that path as if its slope still used calendar months.
            if not np.isfinite(values).all():
                incomplete += 1
                continue
            series = [SeriesPoint(date=date, value=float(value)) for date, value in zip(dates, values)]
            try:
                run_trend(series)
            except TrendError:
                failed += 1
            else:
                tested += 1
    trend_seconds = perf_counter() - start
    full_cells = data.sizes["lat"] * data.sizes["lon"]
    estimate = load_seconds + trend_seconds / tested * full_cells if tested else None
    if tested != box_size**2:
        decision, reason = "retain_subregions", "Not all sample cells completed a valid diagnostic test."
    elif estimate > budget_seconds:
        decision, reason = "retain_subregions", "The serial full-window estimate exceeds the local time budget."
    else:
        decision, reason = "optional_per_cell_trial", "The serial full-window estimate fits the local time budget."
    return {
        "sample": {
            "lat_slice": [row, row + box_size], "lon_slice": [col, col + box_size],
            "cell_count": box_size**2, "months_per_cell": len(dates),
            "latitude_centers": loaded.lat.values.tolist(), "longitude_centers": loaded.lon.values.tolist(),
        },
        "load_seconds": load_seconds, "trend_seconds": trend_seconds,
        "tested_cells": tested, "incomplete_cells": incomplete,
        "failed_cells": failed, "full_window_cells": full_cells,
        "estimated_full_window_seconds": estimate, "budget_seconds": budget_seconds,
        "decision": decision, "decision_reason": reason,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/clean.nc"))
    parser.add_argument("--report", type=Path, default=Path("docs/evidence/day12/chunk_check.json"))
    parser.add_argument("--box-size", type=int, default=4)
    parser.add_argument("--budget-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    source_record = json.loads(Path("docs/evidence/day11/subregion_check.json").read_text())
    if source_hash != source_record["source_sha256"]:
        raise ValueError("Source clean.nc does not match the Day 11 check record.")
    with xr.open_dataset(args.input, engine="netcdf4") as dataset:
        data = chunk_nighttime(dataset)
        expected = np.arange("2003-01", "2025-01", dtype="datetime64[M]")
        if not np.array_equal(np.asarray(data.time.values, dtype="datetime64[M]"), expected):
            raise ValueError("Expected the complete 2003-2024 monthly record.")
        trial = benchmark_cells(data, args.box_size, args.budget_seconds)
        rows, cols = trial["sample"]["lat_slice"], trial["sample"]["lon_slice"]
        direct = dataset.lst_night.transpose("time", "lat", "lon").isel(
            lat=slice(*rows), lon=slice(*cols),
        ).values
        computed = data.isel(lat=slice(*rows), lon=slice(*cols)).compute(scheduler="single-threaded")
        if not np.array_equal(computed.values, direct, equal_nan=True):
            raise ValueError("The chunked sample differs from the direct read.")
        report = {
            "status": "chunking_and_small_box_trial_complete", "source_filename": args.input.name,
            "source_sha256": source_hash, "variable": "lst_night", "units": "degC",
            "first_month": "2003-01", "last_month": "2024-12",
            "source_dimensions": dict(data.sizes), "requested_chunks": REQUESTED_CHUNKS,
            "actual_chunks": {dim: list(sizes) for dim, sizes in data.chunksizes.items()},
            "nighttime_array_bytes": data.nbytes, "scheduler": "single-threaded",
            "method": "Existing earth_system_trend.trend.run_trend on original monthly cell values; timing only",
            "direct_read_check": "All sample values and missing positions matched",
            "estimate": "Observed sample load seconds + sample trend seconds / tested cells * full-window cells",
            **trial,
            "quality_policy": dataset.attrs["quality_policy"],
            "limitations": "Local serial estimate, not a full-window benchmark or scientific method validation.",
            "runtime": {"python": platform.python_version(), "platform": platform.system(),
                        "architecture": platform.machine(), "dask": dask.__version__,
                        "xarray": xr.__version__, "pymannkendall": pymannkendall.__version__},
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Tested {trial['tested_cells']}/{trial['sample']['cell_count']} cells; decision: {trial['decision']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
