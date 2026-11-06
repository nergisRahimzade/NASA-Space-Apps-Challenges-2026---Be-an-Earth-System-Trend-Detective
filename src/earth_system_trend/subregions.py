"""Build one monthly nighttime LST series for each Phoenix subregion."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import xarray as xr

from .aggregate import monthly_series, save_series
from .timeseries import load_timeseries

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.patches import Rectangle


def select_region(dataset: xr.Dataset, bounds: list[float]) -> xr.Dataset:
    if len(bounds) != 4 or not np.isfinite(bounds).all():
        raise ValueError("Bounds must contain four finite coordinates.")
    west, south, east, north = bounds
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("Invalid west, south, east, north bounds.")
    rows = np.flatnonzero((dataset.lat.values >= south) & (dataset.lat.values < north))
    cols = np.flatnonzero((dataset.lon.values >= west) & (dataset.lon.values < east))
    if not len(rows) or not len(cols):
        raise ValueError("Region is empty: no grid-cell centers inside the bounds.")
    return dataset.isel(lat=rows, lon=cols)


def regional_series(dataset: xr.Dataset, definitions: dict) -> dict[str, pd.DataFrame]:
    if not 3 <= len(definitions) <= 5:
        raise ValueError("Define between three and five regions.")
    coverage = np.zeros((dataset.sizes["lat"], dataset.sizes["lon"]), dtype=np.uint8)
    tables = {}
    for region_id, definition in definitions.items():
        if not re.fullmatch(r"[a-z][a-z0-9_]*", region_id):
            raise ValueError("Region IDs must contain lowercase letters, digits or underscores.")
        selected = select_region(dataset, definition["bounds"])
        rows = dataset.indexes["lat"].get_indexer(selected.lat.values)
        cols = dataset.indexes["lon"].get_indexer(selected.lon.values)
        coverage[np.ix_(rows, cols)] += 1
        tables[region_id] = monthly_series(selected)
    if (coverage > 1).any():
        raise ValueError("The regions overlap on source grid-cell centers.")
    if (coverage == 0).any():
        raise ValueError("The regions do not cover the complete source grid.")
    return tables


def plot_regions(dataset: xr.Dataset, definitions: dict, target: Path) -> None:
    colors = ("#c8ddeb", "#f1d4af", "#d5e7cf", "#e0d3e9", "#e9e4bb")
    fig, ax = plt.subplots(figsize=(7, 5.6), layout="constrained")
    for (region_id, definition), color in zip(definitions.items(), colors):
        west, south, east, north = definition["bounds"]
        ax.add_patch(Rectangle((west, south), east-west, north-south,
                               facecolor=color, edgecolor="#444444", linewidth=1.2))
        selected = select_region(dataset, definition["bounds"])
        cells = selected.sizes["lat"] * selected.sizes["lon"]
        ax.text((west+east)/2, (south+north)/2,
                f"{region_id.removeprefix('phoenix_').capitalize()}\n{cells} cells",
                ha="center", va="center", fontsize=12,
                bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "none"})
    lon, lat = np.meshgrid(dataset.lon.values, dataset.lat.values)
    ax.scatter(lon, lat, s=8, color="#333333", alpha=0.45)
    boxes = np.array([item["bounds"] for item in definitions.values()])
    ax.set(xlim=(boxes[:, 0].min(), boxes[:, 2].max()),
           ylim=(boxes[:, 1].min(), boxes[:, 3].max()),
           xlabel="Longitude (degrees east)", ylabel="Latitude (degrees north)",
           title=f"Phoenix study window: {len(definitions)} geographic subregions")
    ax.set_aspect(1 / np.cos(np.deg2rad(float(dataset.lat.mean()))))
    ax.ticklabel_format(useOffset=False)
    fig.supxlabel("Dots show MOD11C3.061 grid-cell centers (0.05° spacing).", fontsize=9)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=180)
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/processed/clean.nc"))
    parser.add_argument("--definitions", type=Path, default=Path("docs/subregions.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--evidence", type=Path, default=Path("docs/evidence/day11"))
    args = parser.parse_args(argv)
    definitions = json.loads(args.definitions.read_text())["regions"]
    source_hash = hashlib.sha256(args.input.read_bytes()).hexdigest()
    day9_record = json.loads(Path("docs/evidence/day9/series_check.json").read_text())
    if source_hash != day9_record["source_sha256"]:
        raise ValueError("Source clean.nc does not match the Day 9 check record.")
    expected = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]
    records, weighted_sum, weight_sum = [], np.zeros(len(expected)), np.zeros(len(expected))
    with xr.open_dataset(args.input, engine="netcdf4") as dataset:
        tables = regional_series(dataset, definitions)
        parent = monthly_series(dataset)
        for region_id, frame in tables.items():
            if frame["date"].tolist() != expected:
                raise ValueError("Expected all 264 study months in each region.")
            target = args.output_dir / f"timeseries_{region_id}.csv"
            save_series(frame, target)
            points = load_timeseries(target)
            actual = np.array([point.value if point.value is not None else np.nan for point in points])
            if ([point.date for point in points] != expected
                    or not np.array_equal(actual, frame["value"].values, equal_nan=True)):
                raise ValueError(f"CSV round trip differs for {region_id}.")
            selected = select_region(dataset, definitions[region_id]["bounds"])
            weights = np.cos(np.deg2rad(selected.lat)).broadcast_like(selected.lst_night)
            valid_weights = weights.where(selected.lst_night.notnull(), 0).sum(["lat", "lon"]).values
            weighted_sum += np.nan_to_num(frame["value"].values) * valid_weights
            weight_sum += valid_weights
            records.append({
                "id": region_id, **definitions[region_id], "filename": target.name,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "cell_count": selected.sizes["lat"] * selected.sizes["lon"],
                "shape": [selected.sizes["lat"], selected.sizes["lon"]], "row_count": len(frame),
                "missing_values": frame.loc[frame["value"].isna(), "date"].tolist(),
            })
        recombined = np.divide(weighted_sum, weight_sum, out=np.full(len(expected), np.nan), where=weight_sum>0)
        if not np.allclose(recombined, parent["value"].values, rtol=0, atol=1e-12, equal_nan=True):
            raise ValueError("The subregions do not reconstruct the complete-window mean.")
        plot_regions(dataset, definitions, args.evidence / "subregions.png")
        report = {
            "status": "subregion_series_saved_and_loaded", "source_filename": args.input.name,
            "source_sha256": source_hash, "definitions_sha256": hashlib.sha256(args.definitions.read_bytes()).hexdigest(),
            "variable": "lst_night", "units": "degC", "first_month": expected[0], "last_month": expected[-1],
            "region_count": len(records), "source_dimensions": dict(dataset.sizes), "regions": records,
            "selection": "Cell centers: west <= lon < east; south <= lat < north",
            "weighting": "cos(deg2rad(lat)); weighted mean over lat and lon; skip NaN",
            "partition": "All 192 source cells assigned exactly once",
            "max_parent_reconstruction_error": float(np.nanmax(np.abs(recombined-parent["value"].values))),
            "quality_policy": dataset.attrs["quality_policy"], "plot_filename": "subregions.png",
            "backend_loader_check": "All region dates and values matched",
        }
    (args.evidence / "subregion_check.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Saved {len(records)} regional CSVs, each with 264 monthly values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
