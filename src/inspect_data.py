"""Inspect one raw MOD11C3.061 HDF4 file and plot its Phoenix nighttime LST."""

import argparse
import calendar
import hashlib
import json
import re
from datetime import date, timedelta
from pathlib import Path

import matplotlib
import numpy as np
import xarray as xr

matplotlib.use("Agg")
from matplotlib import pyplot as plt

YDIM = "YDim:MODIS_MONTHLY_0.05DEG_CMG_LST"
XDIM = "XDim:MODIS_MONTHLY_0.05DEG_CMG_LST"
BOUNDS = (-112.4, 33.2, -111.6, 33.8)


def json_value(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8")
    raise TypeError(f"Unsupported attribute type: {type(value).__name__}")


def metadata_scalar(text, name):
    block = re.search(
        r"\bOBJECT\s*=\s*" + name + r"\s*\n(.*?)\bEND_OBJECT\s*=\s*" + name + r"\b",
        text, re.DOTALL,
    )
    value = re.search(r'^\s*VALUE\s*=\s*("[^"\n]*"|[^\s]+)\s*$', block[1], re.MULTILINE) if block else None
    if value is None:
        raise ValueError(f"Missing CoreMetadata field: {name}")
    return value[1].strip('"')


def verify_sample(dataset, source):
    match = re.fullmatch(r"MOD11C3\.A(\d{4})(\d{3})\.061\.\d+\.hdf", source.name)
    if match is None:
        raise ValueError("Expected an original MOD11C3.061 HDF filename.")
    year, day = map(int, match.groups())
    first = date(year, 1, 1) + timedelta(days=day - 1)
    last = date(year, first.month, calendar.monthrange(year, first.month)[1])
    core = dataset.attrs["CoreMetadata.0"]
    if (first.year != year or first.day != 1
            or metadata_scalar(core, "SHORTNAME") != "MOD11C3"
            or metadata_scalar(core, "VERSIONID") not in ("61", "061")
            or metadata_scalar(core, "RANGEBEGINNINGDATE") != first.isoformat()
            or metadata_scalar(core, "RANGEENDINGDATE") != last.isoformat()):
        raise ValueError("File metadata does not match the product, version or calendar month.")
    if dict(dataset.sizes) != {YDIM: 3600, XDIM: 7200}:
        raise ValueError("Expected the 3600 by 7200 monthly CMG grid.")
    struct = dataset.attrs["StructMetadata.0"]
    checks = (
        "GCTP_GEO" in struct, "HDFE_GD_UL" in struct,
        re.search(r"UpperLeftPointMtrs\s*=\s*\(-180000000(?:\.0+)?,90000000(?:\.0+)?\)", struct),
        re.search(r"LowerRightMtrs\s*=\s*\(180000000(?:\.0+)?,-90000000(?:\.0+)?\)", struct),
    )
    if not all(checks):
        raise ValueError("Unsupported geographic grid or orientation.")
    for variable in dataset.data_vars.values():
        if variable.dims != (YDIM, XDIM):
            raise ValueError("A variable uses unexpected dimensions.")
    return first.isoformat(), last.isoformat()


def grid_coordinates(rows=3600, cols=7200):
    lat = 90.0 - (np.arange(rows) + 0.5) * (180.0 / rows)
    lon = -180.0 + (np.arange(cols) + 0.5) * (360.0 / cols)
    return lat, lon


def decode_for_plot(raw, attrs):
    low, high = attrs["valid_range"]
    valid = (raw != attrs["_FillValue"]) & (raw >= low) & (raw <= high)
    values = raw.astype(np.float64) * float(attrs["scale_factor"])
    values += float(attrs.get("add_offset", 0.0))
    return np.where(valid, values, np.nan)


def plot_map(dataset, period, target):
    lat, lon = grid_coordinates()
    west, south, east, north = BOUNDS
    rows = np.flatnonzero((lat >= south) & (lat < north))
    cols = np.flatnonzero((lon >= west) & (lon < east))
    layer = dataset["LST_Night_CMG"]
    if layer.attrs["units"] != "K":
        raise ValueError("Unexpected temperature unit.")
    raw = layer.isel({YDIM: rows, XDIM: cols}).values
    values = decode_for_plot(raw, layer.attrs)
    if not np.isfinite(values).any():
        raise ValueError("No nonfill, in-range temperatures in the plotting window.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 6), layout="constrained")
    mesh = ax.pcolormesh(lon[cols], lat[rows], values, shading="auto", cmap="inferno")
    fig.colorbar(mesh, ax=ax, label="Nighttime land surface temperature (K)")
    ax.set(xlim=(west, east), ylim=(south, north), xlabel="Longitude (degrees east)",
           ylabel="Latitude (degrees north)",
           title=f"Phoenix study window: nighttime land surface temperature\n{period[:7]} | MOD11C3.061")
    ax.set_aspect(1 / np.cos(np.deg2rad(lat[rows].mean())))
    ax.ticklabel_format(useOffset=False)
    fig.supxlabel("Inspection only: fill/range masked for display; no QC filter.", fontsize=9)
    fig.savefig(target, dpi=180)
    plt.close(fig)
    return {
        "variable": "LST_Night_CMG", "units": "K", "bounding_box": list(BOUNDS),
        "shape": list(values.shape), "nonfill_in_range_cells": int(np.isfinite(values).sum()),
        "display_min": float(np.nanmin(values)), "display_max": float(np.nanmax(values)),
        "quality_filter_applied": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("docs/evidence/day6"))
    args = parser.parse_args(argv)
    # Keep packed integers, QC bytes and bitmaps intact during inspection.
    with xr.open_dataset(
        args.source, engine="netcdf4", mask_and_scale=False, decode_times=False
    ) as dataset:
        start, end = verify_sample(dataset, args.source)
        args.output.mkdir(parents=True, exist_ok=True)
        map_name = f"phoenix_nighttime_lst_{start[:7]}.png"
        plot = plot_map(dataset, start, args.output / map_name)
        with args.source.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        inventory = {
            "source_filename": args.source.name, "source_sha256": checksum,
            "open_options": {"engine": "netcdf4", "mask_and_scale": False, "decode_times": False},
            "period": {"start": start, "end": end}, "dimensions": dict(dataset.sizes),
            "variables": {name: {"dimensions": list(var.dims), "shape": list(var.shape),
                                  "dtype": str(var.dtype), "attributes": dict(var.attrs)}
                          for name, var in dataset.data_vars.items()},
            "global_attributes": dict(dataset.attrs), "map_filename": map_name,
            "map": plot,
        }
        print(dataset)
        text = json.dumps(inventory, default=json_value, indent=2) + "\n"
        print(text, end="")
        (args.output / "sample_inventory.json").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
