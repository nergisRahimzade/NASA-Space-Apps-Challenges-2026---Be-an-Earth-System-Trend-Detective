"""Save the Phoenix monthly nighttime LST series using cosine-latitude weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from .timeseries import load_timeseries


def monthly_series(dataset: xr.Dataset) -> pd.DataFrame:
    data = dataset["lst_night"]
    if set(data.dims) != {"time", "lat", "lon"}:
        raise ValueError("Nighttime LST must have time, lat and lon dimensions.")
    if data.attrs.get("units") != "degC":
        raise ValueError("Expected nighttime LST units of degC.")
    data = data.sortby("time")
    months = np.asarray(data.time.values, dtype="datetime64[M]")
    if not len(months) or np.isnat(months).any():
        raise ValueError("Monthly dates must be present and valid.")
    if len(np.unique(months)) != len(months):
        raise ValueError("Duplicate months in clean data.")
    expected = np.arange(months[0], months[-1] + np.timedelta64(1, "M"), dtype="datetime64[M]")
    if not np.array_equal(months, expected):
        raise ValueError("The input calendar has missing months.")
    if not np.isfinite(data.lat.values).all() or (np.abs(data.lat.values) > 90).any():
        raise ValueError("Latitude must contain finite degree values between -90 and 90.")
    weights = np.cos(np.deg2rad(data.lat))
    mean = data.weighted(weights).mean(["lat", "lon"], skipna=True)
    if np.isinf(mean.values).any():
        raise ValueError("Monthly means cannot contain infinite values.")
    return pd.DataFrame({"date": months.astype(str), "value": mean.values})


def save_series(frame: pd.DataFrame, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="", dir=target.parent,
            prefix=".timeseries-", suffix=".csv", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            frame.to_csv(stream, index=False, na_rep="", float_format="%.17g", lineterminator="\n")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/clean.nc"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/timeseries.csv"))
    parser.add_argument("--report", type=Path, default=Path("docs/evidence/day9/series_check.json"))
    args = parser.parse_args(argv)
    with xr.open_dataset(args.input, engine="netcdf4") as dataset:
        frame = monthly_series(dataset)
        expected = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]
        if frame["date"].tolist() != expected:
            raise ValueError("Expected all 264 study months from 2003-01 through 2024-12.")
        dimensions = dict(dataset.sizes)
        quality_policy = dataset.attrs.get("quality_policy", "Not specified in input")
    save_series(frame, args.output)
    points = load_timeseries(args.output)
    actual = np.array([point.value if point.value is not None else np.nan for point in points])
    if ([point.date for point in points] != expected
            or not np.array_equal(actual, frame["value"].values, equal_nan=True)):
        raise ValueError("Saved CSV values do not match the monthly means.")
    present = frame["value"].notna()
    report = {
        "status": "monthly_series_saved_and_loaded", "region": "Phoenix study area",
        "source_variable": "lst_night", "units": "degC",
        "source_filename": args.input.name,
        "source_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "source_dimensions": dimensions, "output_filename": args.output.name,
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "columns": list(frame.columns), "row_count": len(frame),
        "first_month": expected[0], "last_month": expected[-1],
        "missing_values": frame.loc[~present, "date"].tolist(),
        "min": float(frame["value"].min()) if present.any() else None,
        "max": float(frame["value"].max()) if present.any() else None,
        "weighting": "cos(deg2rad(lat)); weighted mean over lat and lon; skip NaN",
        "quality_policy": quality_policy,
        "backend_loader_check": "All dates and values matched",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Saved {len(frame)} monthly values to {args.output}; units: °C.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
