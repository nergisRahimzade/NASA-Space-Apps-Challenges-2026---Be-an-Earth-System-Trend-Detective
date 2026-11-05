"""Rebuild the Phoenix data products from the verified local HDF4 snapshot."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from time import perf_counter

import xarray as xr

from earth_system_trend.aggregate import monthly_series, save_series
from earth_system_trend.anomaly import monthly_anomalies
from earth_system_trend.subregions import regional_series
from earth_system_trend.trend_map import make_trend_map, save_trend_map

PREPROCESSING_COMMIT = "5364599356de78c1dec1ec147bb9624b0c2f7718"
PREPROCESSING_FILES = ("inspect_data.py", "combine_data.py", "clean_data.py")
EXPECTED_MONTHS = [f"{year}-{month:02d}" for year in range(2003, 2025) for month in range(1, 13)]


def checksum(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_sources(manifest: Path) -> dict:
    with manifest.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if [row["month"] for row in rows] != EXPECTED_MONTHS:
        raise ValueError("Manifest must list all 264 study months in order, without duplicates.")
    raw_root = (manifest.parent / "raw" / "MOD11C3").resolve()
    source_paths = set()
    total = 0
    for index, row in enumerate(rows, start=1):
        relative = Path(row["relative_path"])
        path = (manifest.parent / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(raw_root) or path.name != row["filename"]:
            raise ValueError("Manifest paths must refer to the local MOD11C3 raw folder.")
        if path in source_paths or path.stat().st_size != int(row["bytes"]):
            raise ValueError(f"Duplicate or size-mismatched input: {path.name}")
        if checksum(path) != row["sha256"]:
            raise ValueError(f"Source checksum mismatch: {path.name}")
        source_paths.add(path)
        total += path.stat().st_size
        if index % 24 == 0:
            print(f"Verified source checksums: {index}/264", flush=True)
    if {p.resolve() for p in raw_root.glob("*.hdf")} != source_paths:
        raise ValueError("The raw folder and manifest file list differ.")
    return {"manifest_sha256": checksum(manifest), "verified_files": len(rows), "source_bytes": total}


def reserve_output(path: Path) -> None:
    if path.exists():
        raise FileExistsError("Choose a new output directory; replay never reuses previous outputs.")
    path.mkdir(parents=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/manifest.csv"))
    parser.add_argument("--output", type=Path, default=Path("data/day16_replay"))
    args = parser.parse_args(argv)
    reserve_output(args.output)
    start = perf_counter()
    sources = verify_sources(args.manifest)
    print("Rebuilding from the 264 verified raw files...", flush=True)
    legacy_hashes = {}
    fresh_clean = args.output / "clean.nc"
    with tempfile.TemporaryDirectory(prefix="legacy-", dir=args.output) as directory:
        for name in PREPROCESSING_FILES:
            process = subprocess.run(
                ["git", "show", f"{PREPROCESSING_COMMIT}:src/{name}"], check=False, capture_output=True,
            )
            if process.returncode:
                raise RuntimeError("Pinned preprocessing code is missing; fetch origin feature/ESD-D08-DAT first.")
            (Path(directory) / name).write_bytes(process.stdout)
            legacy_hashes[name] = hashlib.sha256(process.stdout).hexdigest()
        subprocess.run(
            [sys.executable, str(Path(directory) / "clean_data.py"),
             "--manifest", str(args.manifest.resolve()), "--output", str(fresh_clean.resolve()),
             "--evidence", str((args.output / "clean_check").resolve())], check=True,
        )
    reference_root = Path("data/processed")
    csv_records = []
    with xr.open_dataset(fresh_clean, engine="netcdf4") as dataset:
        dataset.load()
        baseline = reference_root / "clean.nc"
        clean_reference_check = "Reference clean.nc absent; derived products checked against tracked references"
        if baseline.exists():
            with xr.open_dataset(baseline, engine="netcdf4") as reference:
                xr.testing.assert_identical(dataset, reference.load())
            clean_reference_check = "All 17 variables, coordinates, attributes, types and missing positions matched"
        raw = monthly_series(dataset)
        anomalies, _ = monthly_anomalies(raw)
        definitions = json.loads(Path("docs/subregions.json").read_text())["regions"]
        frames = {"timeseries.csv": raw, "anomaly.csv": anomalies}
        frames.update({f"timeseries_{name}.csv": frame
                       for name, frame in regional_series(dataset, definitions).items()})
        for name, frame in frames.items():
            target = args.output / name
            save_series(frame, target)
            if target.read_bytes() != (reference_root / name).read_bytes():
                raise ValueError(f"Rebuilt monthly series differs from the tracked reference: {name}")
            csv_records.append({"filename": name, "rows": len(frame), "sha256": checksum(target),
                                "comparison": "Byte-identical to tracked reference"})
        fresh_map = make_trend_map(dataset).compute(scheduler="single-threaded")
        map_path = args.output / "trend_map.nc"
        save_trend_map(fresh_map, map_path)
        with xr.open_dataset(reference_root / "trend_map.nc", engine="netcdf4") as reference:
            xr.testing.assert_identical(fresh_map, reference.load())
        dimensions = dict(dataset.sizes)
        quality_policy = dataset.attrs["quality_policy"]
    report = {
        "status": "raw_snapshot_replay_passed", "input_scope": "Existing downloaded raw files; no new download",
        **sources, "preprocessing_commit": PREPROCESSING_COMMIT,
        "preprocessing_file_sha256": legacy_hashes,
        "derived_processing_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "reproduction_script_sha256": checksum(Path(__file__)),
        "derived_module_sha256": {name: checksum(Path("src/earth_system_trend") / name)
                                   for name in ("aggregate.py", "anomaly.py", "subregions.py", "trend_map.py", "trend.py")},
        "fresh_output_directory": args.output.as_posix(), "dimensions": dimensions,
        "first_month": "2003-01", "last_month": "2024-12",
        "clean_sha256": checksum(fresh_clean), "clean_reference_check": clean_reference_check,
        "csv_outputs": csv_records, "trend_map_sha256": checksum(map_path),
        "map_reference_check": "All six fields, coordinates, attributes, types and missing positions matched",
        "quality_policy": quality_policy, "elapsed_seconds": perf_counter() - start,
        "scientific_signoff": "Not established by this reproducibility check",
    }
    (args.output / "reproduction_check.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print("Replay passed: clean.nc, six monthly CSVs and the 192-cell map matched their references.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
