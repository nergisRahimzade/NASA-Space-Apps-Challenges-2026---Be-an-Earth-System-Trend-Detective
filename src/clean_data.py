"""Decode the monthly MODIS fields and save the fixed Phoenix window."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import xarray as xr
from matplotlib import pyplot as plt
from matplotlib.ticker import MaxNLocator

from combine_data import EXPECTED_MONTHS, check_calendar, manifest_paths, open_combined
from inspect_data import BOUNDS, XDIM, YDIM, grid_coordinates, json_value

FIELD_NAMES = {
    "LST_Day_CMG": "lst_day", "LST_Night_CMG": "lst_night",
    "QC_Day": "qc_day", "QC_Night": "qc_night",
    "Day_view_time": "day_view_time", "Night_view_time": "night_view_time",
    "Day_view_angl": "day_view_angle", "Night_view_angl": "night_view_angle",
    "Clear_sky_days": "clear_sky_days", "Clear_sky_nights": "clear_sky_nights",
    **{f"Emis_{band}": f"emissivity_{band}" for band in (20, 22, 23, 29, 31, 32)},
    "Percent_land_in_grid": "percent_land",
}
FLAGS = {"QC_Day", "QC_Night", "Clear_sky_days", "Clear_sky_nights"}
PLOT_MONTHS = ("2024-01", "2024-05", "2024-07")


def clean_dataset(raw, bounds=BOUNDS):
    if set(raw.data_vars) != set(FIELD_NAMES):
        raise ValueError("Expected all 17 MOD11C3 fields.")
    lat, lon = grid_coordinates()
    if len(lat) != raw.sizes[YDIM] or len(lon) != raw.sizes[XDIM]:
        raise ValueError("Coordinates do not match the source grid.")
    west, south, east, north = bounds
    selected = raw.rename({YDIM: "lat", XDIM: "lon"}).assign_coords(lat=lat, lon=lon)
    selected = selected.sel(lat=slice(north, south), lon=slice(west, east))
    if not selected.sizes["lat"] or not selected.sizes["lon"]:
        raise ValueError("No grid-cell centers inside the study window.")
    clean = xr.Dataset(coords={
        "time": ("time", raw.time.values.copy(), dict(raw.time.attrs)),
        "lat": ("lat", selected.lat.values.copy(),
                {"standard_name": "latitude", "units": "degrees_north", "axis": "Y"}),
        "lon": ("lon", selected.lon.values.copy(),
                {"standard_name": "longitude", "units": "degrees_east", "axis": "X"}),
    }, attrs={
        "title": "Phoenix monthly land surface temperature and supporting fields",
        "source_product": "MOD11C3.061", "study_bounds_west_south_east_north": list(bounds),
        "quality_policy": "Numeric fill and valid range only; production QC filter not applied",
        **{key: raw.attrs[key] for key in ("source_file_count", "time_coverage_start", "time_coverage_end")
           if key in raw.attrs},
    })
    if "identifier_product_doi" in raw.attrs:
        clean.attrs["source_product_doi"] = raw.attrs["identifier_product_doi"]
    for old, new in FIELD_NAMES.items():
        source, attrs = selected[old], selected[old].attrs
        metadata = {"long_name": attrs.get("long_name", new), "source_variable": old,
                    "source_attributes": json.dumps(attrs, default=json_value, sort_keys=True)}
        if old in FLAGS:
            values = source.copy(deep=False)
            metadata["units"] = "1"
        else:
            low, high = attrs["valid_range"]
            valid = (source != attrs["_FillValue"]) & (source >= low) & (source <= high)
            values = source.astype(np.float64).where(valid)
            values = values * float(attrs.get("scale_factor", 1.0)) + float(attrs.get("add_offset", 0.0))
            if old.startswith("LST_"):
                if attrs["units"] != "K":
                    raise ValueError("Expected Kelvin before Celsius conversion.")
                values = values - 273.15
                metadata["units"] = "degC"
            elif old.endswith("view_time"):
                # 'hrs' keeps clock-hour values numeric on a normal xarray reopen.
                metadata.update({"units": "hrs", "time_reference": "UTC"})
            elif old.endswith("view_angl"):
                metadata["units"] = "degrees"
            elif old.startswith("Emis_"):
                metadata["units"] = "1"
            else:
                metadata["units"] = "%"
        values.attrs = metadata
        values.encoding = {"_FillValue": None if old in FLAGS else np.nan}
        clean[new] = values
    for name in clean.coords:
        clean[name].encoding = {"_FillValue": None}
    return clean


def save_clean_dataset(clean, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".clean-", suffix=".nc", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        encoding = {name: {**var.encoding, "zlib": True, "complevel": 4}
                    for name, var in clean.data_vars.items()}
        clean.to_netcdf(temporary, engine="netcdf4", format="NETCDF4", encoding=encoding)
        with xr.open_dataset(temporary, engine="netcdf4") as reopened:
            xr.testing.assert_allclose(reopened, clean)
            for name in clean.data_vars:
                if reopened[name].dtype != clean[name].dtype:
                    raise ValueError(f"Type changed on NetCDF round trip: {name}")
        with xr.open_dataset(temporary, engine="netcdf4", mask_and_scale=False) as stored:
            for variable in stored.data_vars.values():
                if "scale_factor" in variable.attrs or "add_offset" in variable.attrs:
                    raise ValueError("Clean output still advertises packed scaling.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def plot_clean_maps(clean, target):
    maps = [clean.lst_night.sel(time=month + "-01") for month in PLOT_MONTHS]
    low = min(float(layer.min(skipna=True)) for layer in maps)
    high = max(float(layer.max(skipna=True)) for layer in maps)
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.7), sharey=True, layout="constrained")
    for ax, month, layer in zip(axes, PLOT_MONTHS, maps):
        mesh = ax.pcolormesh(clean.lon, clean.lat, layer, shading="auto", cmap="inferno", vmin=low, vmax=high)
        ax.set(title=month, xlim=(BOUNDS[0], BOUNDS[2]), ylim=(BOUNDS[1], BOUNDS[3]))
        ax.set_aspect(1 / np.cos(np.deg2rad(float(clean.lat.mean()))))
        ax.xaxis.set_major_locator(MaxNLocator(4))
        ax.yaxis.set_major_locator(MaxNLocator(4))
        ax.ticklabel_format(useOffset=False)
    fig.colorbar(mesh, ax=list(axes), label="Nighttime land surface temperature (°C)")
    fig.suptitle("Phoenix nighttime land surface temperature | MOD11C3.061", fontsize=14)
    fig.supylabel("Latitude (degrees north)")
    fig.supxlabel("Longitude (degrees east)\nFill/range cleaning only; QC policy pending.", fontsize=10)
    target.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(target, dpi=180)
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/clean.nc"))
    parser.add_argument("--evidence", type=Path, default=Path("docs/evidence/day8"))
    args = parser.parse_args(argv)
    paths = manifest_paths(args.manifest)
    print(f"Opening {len(paths)} monthly source files...", flush=True)
    with open_combined(paths, EXPECTED_MONTHS) as raw:
        print("Cleaning and reading the Phoenix window...", flush=True)
        clean = clean_dataset(raw).compute(scheduler="single-threaded")
    clean.attrs["source_manifest_sha256"] = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    check_calendar(clean.time.values, EXPECTED_MONTHS)
    print("Saving and reopening clean.nc...", flush=True)
    save_clean_dataset(clean, args.output)
    args.evidence.mkdir(parents=True, exist_ok=True)
    with xr.open_dataset(args.output, engine="netcdf4") as reopened:
        plot_clean_maps(reopened, args.evidence / "clean_maps.png")
        variables = {}
        for name, var in reopened.data_vars.items():
            missing = int(var.isnull().sum())
            variables[name] = {"dtype": str(var.dtype), "units": var.attrs["units"],
                               "missing_cells": missing,
                               "min": None if missing == var.size else float(var.min(skipna=True)),
                               "max": None if missing == var.size else float(var.max(skipna=True))}
        empty = reopened.lst_night.isnull().all(["lat", "lon"]).values
        report = {
            "status": "clean_dataset_saved_and_reopened", "product": "MOD11C3.061",
            "output_filename": args.output.name, "output_bytes": args.output.stat().st_size,
            "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            "source_manifest_sha256": clean.attrs["source_manifest_sha256"],
            "dimensions": dict(reopened.sizes), "source_variable_names": FIELD_NAMES,
            "first_month": str(reopened.time.values[0].astype("datetime64[M]")),
            "last_month": str(reopened.time.values[-1].astype("datetime64[M]")),
            "latitude_centers": [float(reopened.lat[0]), float(reopened.lat[-1])],
            "longitude_centers": [float(reopened.lon[0]), float(reopened.lon[-1])],
            "variables": variables, "quality_policy": reopened.attrs["quality_policy"],
            "all_missing_nighttime_months": reopened.time.values[empty].astype("datetime64[M]").astype(str).tolist(),
            "netcdf_roundtrip": "All values, coordinates and types matched",
            "map_filename": "clean_maps.png", "map_months": list(PLOT_MONTHS),
        }
    (args.evidence / "clean_check.json").write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(f"Saved and verified {args.output}: 264 months, 12 x 16 Phoenix cells.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
