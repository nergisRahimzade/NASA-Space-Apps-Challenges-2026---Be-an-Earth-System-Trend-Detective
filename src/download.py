"""Download MOD11C3.061 monthly files for the fixed Phoenix study window."""

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import tempfile
from datetime import UTC, date, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from urllib.parse import urlparse

import earthaccess
from earthaccess.exceptions import LoginAttemptFailure, LoginStrategyUnavailable

SHORT_NAME = "MOD11C3"
VERSION = "061"
BOUNDS = (-112.4, 33.2, -111.6, 33.8)  # west, south, east, north
HDF4_MAGIC = b"\x0e\x03\x13\x01"


class DownloadError(RuntimeError):
    """An incomplete search, login, or download."""


def authenticate(interactive=False):
    strategies = ("interactive",) if interactive else ("netrc", "environment")
    for strategy in strategies:
        try:
            if interactive:
                auth = earthaccess.login(strategy=strategy, persist=False)
            else:
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    auth = earthaccess.login(strategy=strategy, persist=False)
        except (LoginAttemptFailure, LoginStrategyUnavailable):
            auth = None
        if auth is not None and auth.authenticated:
            return
    raise DownloadError("Earthdata login required. Run again with --interactive.")


def filename(granule):
    names = {
        Path(urlparse(url).path).name
        for url in granule.data_links(access="external")
        if urlparse(url).scheme == "https" and urlparse(url).path.endswith(".hdf")
    }
    if len(names) != 1:
        raise DownloadError("Expected one HDF4 science file per granule.")
    name = names.pop()
    if not name.startswith(f"{SHORT_NAME}.A") or f".{VERSION}." not in name:
        raise DownloadError("Search returned an unexpected product or version.")
    return name


def catalogue_size(granule, name):
    records = granule["umm"]["DataGranule"]["ArchiveAndDistributionInformation"]
    matching = [record for record in records if Path(record.get("Name", "")).name == name]
    if not matching and len(records) == 1:
        matching = records
    if len(matching) != 1:
        raise DownloadError("Cannot identify the science file's catalogue size.")
    record = matching[0]
    if record.get("SizeInBytes"):
        return int(record["SizeInBytes"]), 0
    factors = {"B": 1, "BYTES": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
    factor = factors.get(str(record.get("SizeUnit", "")).upper())
    if factor is None or not record.get("Size"):
        raise DownloadError("Catalogue file size or units are unavailable.")
    amount = Decimal(str(record["Size"]))
    # Permit only the rounding uncertainty of the reported metadata value.
    quantum = Decimal(10) ** amount.as_tuple().exponent
    tolerance = max(1, int((quantum * factor / 2).to_integral_value(rounding=ROUND_CEILING)))
    return int((amount * factor).to_integral_value()), tolerance


def check_file(path, expected_bytes, tolerance):
    if not path.is_file() or path.stat().st_size <= 4:
        raise DownloadError(f"Missing or empty download: {path.name}")
    with path.open("rb") as stream:
        if stream.read(4) != HDF4_MAGIC:
            raise DownloadError(f"Download is not HDF4: {path.name}")
    if abs(path.stat().st_size - expected_bytes) > tolerance:
        raise DownloadError(f"Download size differs from the catalogue: {path.name}")


def calendar_months(start, end):
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise DownloadError("Start date must not be after end date.")
    return [
        f"{index // 12:04d}-{index % 12 + 1:02d}"
        for index in range(first.year * 12 + first.month - 1, last.year * 12 + last.month)
    ]


def write_manifest(report, output_dir, manifest_path):
    expected = calendar_months(report["period"]["start"], report["period"]["end"])
    records = report.get("files", [])
    months = [record["month"] for record in records]
    if (report.get("status") != "files_verified"
            or report.get("verified_count") != len(expected)
            or len(records) != len(expected) or sorted(months) != expected):
        raise DownloadError("Manifest requires exactly one verified file for every requested month.")
    names = [record["filename"] for record in records]
    output_dir, manifest_path = Path(output_dir).resolve(), Path(manifest_path).resolve()
    actual = {path.name for path in output_dir.glob("*.hdf") if path.is_file()}
    if len(set(names)) != len(expected) or actual != set(names):
        raise DownloadError("HDF4 files on disk do not match the complete monthly file list.")
    rows = []
    for record in sorted(records, key=lambda item: item["month"]):
        path = output_dir / record["filename"]
        if path.stat().st_size != record["bytes"]:
            raise DownloadError(f"File changed since verification: {path.name}")
        rows.append({
            "month": record["month"], "filename": path.name,
            "relative_path": Path(os.path.relpath(path, manifest_path.parent)).as_posix(),
            "bytes": record["bytes"], "sha256": record["sha256"],
        })
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", newline="", encoding="utf-8", dir=manifest_path.parent,
            prefix=".manifest-", suffix=".tmp", delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(
                stream, fieldnames=["month", "filename", "relative_path", "bytes", "sha256"],
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(rows)
        temporary.replace(manifest_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(rows)


def download_samples(start, end, count, output_dir, interactive=False):
    if count < 1 or date.fromisoformat(start) > date.fromisoformat(end):
        raise DownloadError("Use a positive count and a valid start/end date range.")
    granules = earthaccess.search_data(
        short_name=SHORT_NAME,
        version=VERSION,
        provider="LPCLOUD",
        temporal=(start, end),
        bounding_box=BOUNDS,
        sort_key="start_date",
        count=count,
    )
    if len(granules) != count:
        raise DownloadError(f"Expected {count} monthly files; found {len(granules)}.")
    names = [filename(granule) for granule in granules]
    sizes = [catalogue_size(granule, name) for granule, name in zip(granules, names)]
    months = [
        granule["umm"]["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:7]
        for granule in granules
    ]
    if len(set(names)) != count or len(set(months)) != count:
        raise DownloadError("Search returned duplicate filenames or months.")
    if count == len(calendar_months(start, end)) and sorted(months) != calendar_months(start, end):
        raise DownloadError("Search did not return every month in the requested period.")

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = set()
    missing = []
    for granule, name, size in zip(granules, names, sizes):
        path = output_dir / name
        if path.exists():
            check_file(path, *size)
            existing.add(name)
        else:
            missing.append(granule)

    if missing:
        print(f"Found {count} monthly files: {len(existing)} existing, {len(missing)} to download.")
        authenticate(interactive=interactive)
        paths = earthaccess.download(
            missing, local_path=output_dir, threads=min(3, len(missing)), show_progress=interactive
        )
        expected = {output_dir / name for name in names if name not in existing}
        returned = {Path(path).resolve() for path in paths}
        if len(paths) != len(missing) or returned != expected:
            raise DownloadError("Download returned fewer or different files than requested.")

    records = []
    for name, month, size in zip(names, months, sizes):
        path = output_dir / name
        check_file(path, *size)
        with path.open("rb") as stream:
            checksum = hashlib.file_digest(stream, "sha256").hexdigest()
        records.append({
            "filename": name, "month": month, "bytes": path.stat().st_size,
            "catalogue_bytes": size[0], "size_rounding_tolerance_bytes": size[1],
            "sha256": checksum, "already_present": name in existing,
        })
    return {
        "status": "files_verified",
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "product": f"{SHORT_NAME}.{VERSION}",
        "bounding_box": list(BOUNDS), "period": {"start": start, "end": end},
        "requested_count": count, "verified_count": len(records),
        "new_download_count": len(missing), "reused_count": len(existing),
        "checks": ["expected filenames", "distinct months", "catalogue sizes", "HDF4 signatures"],
        "files": records,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2003-01-01", help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", default="2003-03-31", help="End date, YYYY-MM-DD")
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("data/raw/day4_sample"))
    parser.add_argument("--report", type=Path, default=Path("data/day4_download_check.json"))
    parser.add_argument("--manifest", type=Path, help="Write a complete monthly CSV after verification")
    parser.add_argument("--interactive", action="store_true", help="Log in once before the batch")
    args = parser.parse_args(argv)
    status = 0
    try:
        report = download_samples(args.start, args.end, args.count, args.output, args.interactive)
        if args.manifest:
            report["manifest_rows"] = write_manifest(report, args.output, args.manifest)
    except DownloadError as error:
        print(f"Download failed: {error}")
        report = {"status": "failed", "error_type": type(error).__name__,
                  "checked_at_utc": datetime.now(UTC).isoformat()}
        status = 1
    except Exception as error:  # noqa: BLE001 - redact third-party authentication errors
        # Avoid exposing authentication material in third-party exception text.
        print(f"Download failed ({type(error).__name__}). No successful batch recorded.")
        report = {"status": "failed", "error_type": type(error).__name__,
                  "checked_at_utc": datetime.now(UTC).isoformat()}
        status = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if status == 0:
        print(f"Verified {report['verified_count']} files: {report['new_download_count']} new, "
              f"{report['reused_count']} already present. Report: {args.report}")
        if args.manifest:
            print(f"Manifest: {args.manifest} ({report['manifest_rows']} months)")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
