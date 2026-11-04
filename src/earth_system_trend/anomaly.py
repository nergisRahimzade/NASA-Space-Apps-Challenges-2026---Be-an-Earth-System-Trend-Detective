"""Remove the calendar-month mean using the confirmed 2003-2024 baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import xarray as xr

from .aggregate import save_series
from .timeseries import load_timeseries

matplotlib.use("Agg")
from matplotlib import pyplot as plt

BASELINE_START = "2003-01"
BASELINE_END = "2024-12"


def monthly_anomalies(
    frame: pd.DataFrame, baseline_start: str = BASELINE_START, baseline_end: str = BASELINE_END,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(frame["date"], format="%Y-%m")
    months = np.asarray(dates.values, dtype="datetime64[M]")
    if not len(months) or np.isnat(months).any():
        raise ValueError("Monthly dates must be present and valid.")
    if len(np.unique(months)) != len(months):
        raise ValueError("Duplicate months in the input series.")
    order = np.argsort(months)
    months = months[order]
    expected = np.arange(months[0], months[-1] + np.timedelta64(1, "M"), dtype="datetime64[M]")
    if not np.array_equal(months, expected):
        raise ValueError("The input calendar has missing months.")
    start = pd.to_datetime(baseline_start, format="%Y-%m")
    end = pd.to_datetime(baseline_end, format="%Y-%m")
    if start > end:
        raise ValueError("Baseline start must not be after baseline end.")
    values = np.asarray(frame["value"], dtype=float)[order]
    if np.isinf(values).any():
        raise ValueError("Input values cannot be infinite.")
    series = xr.DataArray(values, dims="time", coords={"time": dates.values[order]})
    baseline = series.sel(time=slice(start, end))
    if not baseline.sizes["time"]:
        raise ValueError("Baseline has no overlap with the input series.")
    counts = baseline.groupby("time.month").count().reindex(month=np.arange(1, 13), fill_value=0)
    means = baseline.groupby("time.month").mean(skipna=True).reindex(month=np.arange(1, 13))
    # Match the frontend: a calendar month needs at least two known baseline values.
    means = means.where(counts >= 2)
    anomaly = series.groupby("time.month") - means
    result = pd.DataFrame({"date": months.astype(str), "value": anomaly.values})
    climatology = pd.DataFrame({"month": np.arange(1, 13), "mean": means.values,
                               "count": counts.values.astype(int)})
    return result, climatology


def plot_comparison(raw: pd.DataFrame, anomaly: pd.DataFrame, target: Path) -> None:
    dates = pd.to_datetime(raw["date"], format="%Y-%m")
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5), sharex=True, layout="constrained")
    axes[0].plot(dates, raw["value"], color="#276b91", linewidth=1.2)
    axes[0].set(title="Original monthly values", ylabel="LST (°C)")
    axes[1].plot(dates, anomaly["value"], color="#b85436", linewidth=1.2)
    axes[1].axhline(0, color="#666666", linewidth=0.8)
    axes[1].set(title="Monthly anomalies", ylabel="Anomaly (°C)", xlabel="Year")
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.margins(x=0.01)
    fig.suptitle("Phoenix nighttime land surface temperature", fontsize=14)
    fig.supxlabel("Baseline: 2003–2024 calendar-month means | MOD11C3.061\n"
                  "Fill/range cleaning only; QC policy pending.", fontsize=9)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/timeseries.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/anomaly.csv"))
    parser.add_argument("--source-report", type=Path, default=Path("docs/evidence/day9/series_check.json"))
    parser.add_argument("--evidence", type=Path, default=Path("docs/evidence/day10"))
    args = parser.parse_args(argv)
    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    source_record = json.loads(args.source_report.read_text())
    if source_record["output_sha256"] != source_hash:
        raise ValueError("The source CSV does not match its Day 9 check record.")
    raw = pd.DataFrame([point.model_dump() for point in load_timeseries(args.input)])
    expected = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]
    if raw["date"].tolist() != expected:
        raise ValueError("Expected the complete 2003-2024 monthly series.")
    anomaly, climatology = monthly_anomalies(raw)
    save_series(anomaly, args.output)
    reopened = load_timeseries(args.output)
    values = np.array([point.value if point.value is not None else np.nan for point in reopened])
    if ([point.date for point in reopened] != expected
            or not np.array_equal(values, anomaly["value"].values, equal_nan=True)):
        raise ValueError("Saved anomalies do not match the calculated values.")
    plot_comparison(raw, anomaly, args.evidence / "raw_vs_anomaly.png")
    residual_means = anomaly.groupby(pd.to_datetime(anomaly["date"]).dt.month)["value"].mean()
    present = anomaly["value"].notna()
    report = {
        "status": "anomaly_series_saved_and_loaded", "source_filename": args.input.name,
        "source_sha256": source_hash, "output_filename": args.output.name,
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "row_count": len(anomaly), "first_month": expected[0], "last_month": expected[-1],
        "units": "degC", "definition": "Value minus the baseline mean for the same calendar month",
        "baseline": {"start": BASELINE_START, "end": BASELINE_END, "minimum_samples_per_month": 2},
        "climatology": [{"month": int(row.month), "mean": float(row.mean) if pd.notna(row.mean) else None,
                         "count": int(row.count)} for row in climatology.itertuples(index=False)],
        "missing_values": anomaly.loc[~present, "date"].tolist(),
        "min": float(anomaly["value"].min()) if present.any() else None,
        "max": float(anomaly["value"].max()) if present.any() else None,
        "max_abs_calendar_month_mean": float(residual_means.abs().max()) if present.any() else None,
        "quality_policy": source_record["quality_policy"], "plot_filename": "raw_vs_anomaly.png",
        "backend_loader_check": "All dates and values matched",
    }
    (args.evidence / "anomaly_check.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"Saved {len(anomaly)} monthly anomalies to {args.output}; baseline: 2003–2024.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
