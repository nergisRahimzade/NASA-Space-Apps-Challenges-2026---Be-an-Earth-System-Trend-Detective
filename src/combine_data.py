"""Open the complete MOD11C3.061 record as one raw, lazy monthly dataset."""

import argparse
import calendar
import csv
import hashlib
import json
from datetime import date
from pathlib import Path

import numpy as np
import xarray as xr

from inspect_data import XDIM, YDIM, json_value, verify_sample

RAW_OPTIONS = {"engine": "netcdf4", "mask_and_scale": False, "decode_times": False}
EXPECTED_MONTHS = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]


def check_calendar(times, expected_months):
    months = np.asarray(times, dtype="datetime64[M]")
    expected = np.asarray(expected_months, dtype="datetime64[M]")
    if len(np.unique(months)) != len(months):
        raise ValueError("Duplicate months in the source calendar.")
    if not np.array_equal(np.sort(months), expected):
        raise ValueError("Monthly calendar has missing or unexpected months.")


def manifest_paths(manifest):
    with manifest.open(newline="", encoding="utf-8") as stream:
        records = list(csv.DictReader(stream))
    check_calendar([row["month"] for row in records], EXPECTED_MONTHS)
    paths = []
    for row in records:
        path = (manifest.parent / row["relative_path"]).resolve()
        if path.name != row["filename"] or path.stat().st_size != int(row["bytes"]):
            raise ValueError(f"File does not match the manifest: {row['filename']}")
        paths.append(path)
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate source paths in manifest.")
    actual = {path.name for path in paths[0].parent.glob("*.hdf")}
    if actual != {path.name for path in paths}:
        raise ValueError("Source folder does not match the manifest file list.")
    return paths


def normalized(value):
    return json.loads(json.dumps(value, default=json_value, sort_keys=True))


def open_combined(paths, expected_months):
    paths = [Path(path).resolve() for path in paths]
    dates, schema, first_globals, conflicts = {}, None, None, set()
    for path in paths:
        with xr.open_dataset(path, **RAW_OPTIONS) as source:
            start, _ = verify_sample(source, path)
            if path in dates:
                raise ValueError("Duplicate source paths.")
            dates[path] = start
            current = {name: {"dimensions": list(var.dims), "shape": list(var.shape),
                              "dtype": str(var.dtype), "attributes": normalized(dict(var.attrs))}
                       for name, var in source.data_vars.items()}
            if schema is None:
                schema = current
            elif current != schema:
                raise ValueError(f"Variable metadata differs between monthly files: {path.name}")
            attrs = normalized(dict(source.attrs))
            if first_globals is None:
                first_globals = attrs
            else:
                conflicts.update(key for key in first_globals.keys() | attrs.keys()
                                 if first_globals.get(key) != attrs.get(key))
    check_calendar(list(dates.values()), expected_months)

    def add_time(source):
        start = dates[Path(source.encoding["source"]).resolve()]
        return source.expand_dims(time=[np.datetime64(start, "ns")])

    combined = xr.open_mfdataset(
        paths, **RAW_OPTIONS, combine="by_coords", preprocess=add_time,
        chunks={YDIM: 180, XDIM: 7200}, parallel=False,
        data_vars="minimal", coords="minimal", compat="equals", join="exact",
        combine_attrs="drop_conflicts",
    )
    try:
        check_calendar(combined.time.values, expected_months)
        start, last = min(dates.values()), date.fromisoformat(max(dates.values()))
        end = last.replace(day=calendar.monthrange(last.year, last.month)[1]).isoformat()
        combined.attrs.update({
            "time_coverage_start": start, "time_coverage_end": end,
            "source_file_count": len(paths),
            "source_global_attribute_conflicts": sorted(conflicts),
        })
        combined.time.attrs.update({"standard_name": "time", "axis": "T",
                                    "long_name": "Calendar-month start"})
    except Exception:
        combined.close()
        raise
    return combined


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.csv"))
    parser.add_argument("--report", type=Path, default=Path("docs/evidence/day7/combined_check.json"))
    args = parser.parse_args(argv)
    paths = manifest_paths(args.manifest)
    print(f"Checking and combining {len(paths)} monthly files...", flush=True)
    with open_combined(paths, EXPECTED_MONTHS) as combined:
        # Prove every monthly source can supply raw data without loading the global cube.
        sample = combined["LST_Night_CMG"].isel({YDIM: 1124, XDIM: 1352})
        sample = sample.compute(scheduler="single-threaded")
        report = {
            "status": "combined_dataset_opened", "product": "MOD11C3.061",
            "source_manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "source_file_count": len(paths), "dimensions": dict(combined.sizes),
            "period": {"start": combined.attrs["time_coverage_start"],
                       "end": combined.attrs["time_coverage_end"]},
            "months": combined.time.values.astype("datetime64[M]").astype(str).tolist(),
            "missing_months": [], "duplicate_months": [],
            "combine_options": {**RAW_OPTIONS, "combine": "by_coords", "parallel": False,
                                "combine_attrs": "drop_conflicts",
                                "chunks": {YDIM: 180, XDIM: 7200}},
            "variables": {name: {"dimensions": list(var.dims), "dtype": str(var.dtype),
                                  "attributes": normalized(dict(var.attrs))}
                          for name, var in combined.data_vars.items()},
            "variable_metadata_consistent": True,
            "global_attributes": normalized(dict(combined.attrs)),
            "data_read_check": {"variable": "LST_Night_CMG", "source_row": 1124,
                                "source_column": 1352, "months_read": int(sample.size),
                                "raw_dtype": str(sample.dtype),
                                "first_raw_value": int(sample.values[0]),
                                "last_raw_value": int(sample.values[-1]),
                                "raw_values_sha256": hashlib.sha256(sample.values.tobytes()).hexdigest()},
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, default=json_value, indent=2) + "\n", encoding="utf-8")
        print(combined)
        print(f"Verified {combined.sizes['time']} months; no gaps or duplicates. Report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
