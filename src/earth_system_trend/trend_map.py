"""Build the optional small-window trend map for ESD-D13-DAT."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from time import perf_counter

import matplotlib
import numpy as np
import xarray as xr

from .chunk_check import chunk_nighttime
from .contract import SeriesPoint
from .trend import MIN_VALUES, TrendError, run_trend

matplotlib.use("Agg")
from matplotlib import pyplot as plt

FIELDS = ("slope", "p", "tau", "direction", "n_valid", "status")
DIRECTION = {"decreasing": -1, "no trend": 0, "increasing": 1}


def cell_statistics(values: np.ndarray, dates: list[str]) -> tuple:
    valid = int(np.isfinite(values).sum())
    if len(values) != len(dates):
        raise ValueError("Each value must have its original calendar month.")
    if len(values) < MIN_VALUES:
        return np.nan, np.nan, np.nan, 2, valid, 2
    if valid != len(values):
        return np.nan, np.nan, np.nan, 2, valid, 1
    points = [SeriesPoint(date=date, value=float(value)) for date, value in zip(dates, values)]
    try:
        result = run_trend(points)
    except TrendError:
        return np.nan, np.nan, np.nan, 2, valid, 3
    return result.slope, result.p, result.tau, DIRECTION[result.trend], valid, 0


def make_trend_map(dataset: xr.Dataset) -> xr.Dataset:
    data = chunk_nighttime(dataset)
    dates = np.asarray(data.time.values, dtype="datetime64[M]").astype(str).tolist()
    outputs = xr.apply_ufunc(
        cell_statistics, data, kwargs={"dates": dates}, input_core_dims=[["time"]],
        output_core_dims=[[] for _ in FIELDS], vectorize=True, dask="parallelized",
        output_dtypes=[np.float64, np.float64, np.float64, np.int8, np.int16, np.int8],
    )
    result = xr.Dataset(dict(zip(FIELDS, outputs)))
    result.slope.attrs = {"long_name": "Sen slope of original monthly nighttime LST", "units": "degC month-1"}
    result.p.attrs = {"long_name": "Unadjusted original Mann-Kendall p-value", "units": "1"}
    result.tau.attrs = {"long_name": "Kendall tau", "units": "1"}
    result.direction.attrs = {
        "long_name": "Direction returned by the existing trend function",
        "flag_values": np.array([-1, 0, 1, 2], dtype=np.int8),
        "flag_meanings": "decreasing no_trend increasing not_computed",
    }
    result.n_valid.attrs = {"long_name": "Number of finite monthly values", "units": "1"}
    result.status.attrs = {
        "flag_values": np.array([0, 1, 2, 3], dtype=np.int8),
        "flag_meanings": "computed incomplete_record short_record trend_error",
    }
    result.attrs = {
        "title": "Preliminary Phoenix monthly nighttime LST trend map",
        "source_variable": "lst_night", "period_start": dates[0], "period_end": dates[-1],
        "method": "Existing earth_system_trend.trend.run_trend; pymannkendall.original_test",
        "input_series": "Original monthly values; no anomaly transform",
        "precision": "Backend precision: slope and p rounded to 4 decimals; tau to 3 decimals",
        "quality_policy": dataset.attrs.get("quality_policy", "Not specified in input"),
        "review_status": "Preliminary; production QC and scientific method review pending",
        "missing_policy": "Require a finite value for every month; otherwise leave metrics missing",
    }
    return result


def save_trend_map(result: xr.Dataset, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".nc", delete=False) as stream:
            temporary = Path(stream.name)
        encoding = {name: {"zlib": True, "complevel": 4, "_FillValue": None}
                    for name in result.data_vars}
        result.to_netcdf(temporary, engine="netcdf4", format="NETCDF4", encoding=encoding)
        with xr.open_dataset(temporary, engine="netcdf4") as reopened:
            xr.testing.assert_identical(reopened.load(), result)
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def plot_map(result: xr.Dataset, target: Path) -> None:
    limit = max(float(np.nanmax(np.abs(result.slope.values))), 0.0001)
    fig, ax = plt.subplots(figsize=(8, 5.4), layout="constrained")
    mesh = ax.pcolormesh(result.lon, result.lat, result.slope, shading="nearest",
                         cmap="RdBu_r", vmin=-limit, vmax=limit)
    fig.colorbar(mesh, ax=ax, label="Sen slope (°C per month)")
    ax.set(xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)",
           title="Phoenix nighttime LST: preliminary raw-series trend\n2003-2024 | MOD11C3.061")
    ax.ticklabel_format(useOffset=False)
    ax.set_aspect(1 / np.cos(np.deg2rad(float(result.lat.mean()))))
    fig.supxlabel("Existing original Mann-Kendall method; QC and scientific method review pending.", fontsize=9)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/clean.nc"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/trend_map.nc"))
    parser.add_argument("--evidence", type=Path, default=Path("docs/evidence/day13"))
    parser.add_argument("--budget-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    if not np.isfinite(args.budget_seconds) or args.budget_seconds <= 0:
        raise ValueError("The time budget must be positive and finite.")
    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    prior = json.loads(Path("docs/evidence/day12/chunk_check.json").read_text())
    if source_hash != prior["source_sha256"]:
        raise ValueError("Source clean.nc does not match the Day 12 check record.")
    report = {
        "source_filename": args.input.name, "source_sha256": source_hash,
        "budget_seconds": args.budget_seconds, "scheduler": "single-threaded",
        "method": "xr.apply_ufunc(vectorize=True, dask='parallelized'); existing run_trend on original monthly values",
    }
    with xr.open_dataset(args.input, engine="netcdf4") as dataset:
        data = chunk_nighttime(dataset)
        expected = np.arange("2003-01", "2025-01", dtype="datetime64[M]")
        if not np.array_equal(np.asarray(data.time.values, dtype="datetime64[M]"), expected):
            raise ValueError("Expected the complete 2003-2024 monthly record.")
        row, col = (data.sizes["lat"] - 4) // 2, (data.sizes["lon"] - 4) // 2
        start = perf_counter()
        sample = make_trend_map(dataset.isel(lat=slice(row, row+4), lon=slice(col, col+4)))
        sample = sample.compute(scheduler="single-threaded")
        report["sample_seconds"] = perf_counter() - start
        report["sample_dimensions"] = dict(sample.sizes)
        report["sample_index_slices"] = {"lat": [row, row+4], "lon": [col, col+4]}
        if report["sample_seconds"] <= args.budget_seconds:
            start = perf_counter()
            result = make_trend_map(dataset).compute(scheduler="single-threaded")
            report["full_window_seconds"] = perf_counter() - start
            report["source_dimensions"] = dict(data.sizes)
            report["cell_count"] = data.sizes["lat"] * data.sizes["lon"]
            xr.testing.assert_identical(result.isel(lat=slice(row, row+4), lon=slice(col, col+4)), sample)
            report["sample_full_window_check"] = "All six fields matched"
        else:
            result = None
        if result is None or report["full_window_seconds"] > args.budget_seconds:
            report.update(status="skipped", decision="Retain the four subregions; per-cell trial exceeded the local budget.")
        else:
            if not (result.status.values == 0).any():
                raise ValueError("No cells produced a trend; retain the subregions.")
            save_trend_map(result, args.output)
            plot_map(result, args.evidence / "trend_map.png")
            report.update(
                status="trend_map_saved_and_loaded", decision="Keep the optional Phoenix per-cell map.",
                output_filename=args.output.name,
                output_sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                output_bytes=args.output.stat().st_size, fields=list(result.data_vars),
                dimensions=dict(result.sizes), first_month="2003-01", last_month="2024-12",
                computed_cells=int((result.status.values == 0).sum()),
                status_counts={str(code): int((result.status.values == code).sum()) for code in range(4)},
                min_slope=float(result.slope.min()), max_slope=float(result.slope.max()),
                slope_units=result.slope.attrs["units"], quality_policy=result.attrs["quality_policy"],
                review_status=result.attrs["review_status"], plot_filename="trend_map.png",
                netcdf_readback="All values, coordinates, flags and attributes matched",
            )
    args.evidence.mkdir(parents=True, exist_ok=True)
    (args.evidence / "trend_map_check.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Day 13: {report['status']}; {report['decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
