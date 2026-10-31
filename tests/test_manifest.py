import calendar
import csv
import hashlib
import importlib.util
from datetime import date
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "manifest_download", Path(__file__).resolve().parents[1] / "src" / "download.py"
)
downloader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(downloader)


def make_report(tmp_path, months):
    output = tmp_path / "data" / "raw" / "MOD11C3"
    output.mkdir(parents=True)
    records = []
    for month in months:
        first_day = date.fromisoformat(month + "-01")
        day_of_year = first_day.timetuple().tm_yday
        name = f"MOD11C3.A{first_day.year}{day_of_year:03d}.061.2026001000000.hdf"
        content = downloader.HDF4_MAGIC + month.encode("ascii")
        (output / name).write_bytes(content)
        records.append({
            "month": month,
            "filename": name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        })
    last = date.fromisoformat(months[-1] + "-01")
    report = {
        "status": "files_verified",
        "verified_count": len(records),
        "period": {
            "start": months[0] + "-01",
            "end": f"{months[-1]}-{calendar.monthrange(last.year, last.month)[1]:02d}",
        },
        "files": records,
    }
    return report, output, tmp_path / "data" / "manifest.csv"


def test_manifest_contains_all_264_months_in_order_with_portable_paths(tmp_path):
    months = [f"{year}-{month:02d}" for year in range(2003, 2025)
              for month in range(1, 13)]
    report, output, target = make_report(tmp_path, months)
    report["files"].reverse()

    assert downloader.write_manifest(report, output, target) == 264

    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        assert reader.fieldnames == ["month", "filename", "relative_path", "bytes", "sha256"]
    assert len(rows) == 264
    assert [row["month"] for row in rows] == months
    expected = {record["month"]: record for record in report["files"]}
    for row in rows:
        record = expected[row["month"]]
        assert row["filename"] == record["filename"]
        assert row["relative_path"] == f"raw/MOD11C3/{record['filename']}"
        assert not Path(row["relative_path"]).is_absolute()
        assert int(row["bytes"]) == record["bytes"]
        assert row["sha256"] == record["sha256"]
        assert (target.parent / row["relative_path"]).is_file()


@pytest.mark.parametrize("problem", ["missing_month", "unexpected_month", "duplicate_month"])
def test_incomplete_calendar_never_produces_a_manifest(tmp_path, problem):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    if problem == "missing_month":
        report["files"].pop(1)
        report["verified_count"] -= 1
    elif problem == "unexpected_month":
        # The count remains three, but one expected month has been replaced.
        report["files"][0]["month"] = "2002-12"
    else:
        report["files"][2]["month"] = "2003-01"

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert not target.exists()


def test_missing_physical_file_is_rejected(tmp_path):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    (output / report["files"][1]["filename"]).unlink()

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert not target.exists()


def test_extra_hdf_file_is_not_ignored(tmp_path):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    (output / "unexpected.hdf").write_bytes(downloader.HDF4_MAGIC + b"extra")

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert not target.exists()


def test_file_changed_since_download_report_is_rejected(tmp_path):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    file_path = output / report["files"][0]["filename"]
    file_path.write_bytes(file_path.read_bytes() + b"changed")

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert not target.exists()


def test_failed_validation_preserves_existing_manifest(tmp_path):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    previous = "previous verified manifest\n"
    target.write_text(previous, encoding="utf-8")
    report["files"][1]["month"] = "2003-01"

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert target.read_text(encoding="utf-8") == previous


def test_failed_download_report_cannot_become_a_verified_manifest(tmp_path):
    report, output, target = make_report(tmp_path, ["2003-01", "2003-02", "2003-03"])
    report["status"] = "failed"

    with pytest.raises(downloader.DownloadError):
        downloader.write_manifest(report, output, target)
    assert not target.exists()
