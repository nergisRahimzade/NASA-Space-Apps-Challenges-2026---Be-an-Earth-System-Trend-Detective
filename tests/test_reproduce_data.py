"""Verify raw snapshot identity before allowing a fresh reproducibility run."""

import csv
import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "reproduce_data", Path(__file__).resolve().parents[1] / "scripts" / "reproduce_data.py"
)
reproducer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reproducer)


def write_manifest(path, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["month", "filename", "relative_path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def snapshot(tmp_path, monkeypatch):
    months = ["2003-01", "2003-02", "2003-03"]
    monkeypatch.setattr(reproducer, "EXPECTED_MONTHS", months)
    raw = tmp_path / "data" / "raw" / "MOD11C3"
    raw.mkdir(parents=True)
    rows = []
    for index, month in enumerate(months):
        filename = f"sample_{month}.hdf"
        content = f"raw{index}".encode()
        (raw / filename).write_bytes(content)
        rows.append({"month": month, "filename": filename, "relative_path": f"raw/MOD11C3/{filename}",
                     "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    manifest = tmp_path / "data" / "manifest.csv"
    write_manifest(manifest, rows)
    return manifest, raw, rows


def test_verified_snapshot_reports_identity_and_rejects_same_size_byte_change(snapshot):
    manifest, raw, rows = snapshot

    report = reproducer.verify_sources(manifest)

    assert report == {"manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                      "verified_files": 3, "source_bytes": 12}
    changed = raw / rows[0]["filename"]
    changed.write_bytes(b"edit")
    assert changed.stat().st_size == rows[0]["bytes"]
    with pytest.raises(ValueError, match="checksum mismatch"):
        reproducer.verify_sources(manifest)


@pytest.mark.parametrize("problem", ["missing", "duplicate", "out_of_order"])
def test_manifest_calendar_must_be_complete_unique_and_ordered(snapshot, problem):
    manifest, _, rows = snapshot
    if problem == "missing":
        del rows[1]
    elif problem == "duplicate":
        rows[1]["month"] = rows[0]["month"]
    else:
        rows[0], rows[1] = rows[1], rows[0]
    write_manifest(manifest, rows)

    with pytest.raises(ValueError, match="months in order"):
        reproducer.verify_sources(manifest)


@pytest.mark.parametrize("problem", ["extra_hdf", "escape", "absolute", "duplicate_file"])
def test_raw_files_and_manifest_paths_must_match_exactly(snapshot, problem):
    manifest, raw, rows = snapshot
    if problem == "extra_hdf":
        (raw / "unexpected.hdf").write_bytes(b"extra")
    elif problem == "escape":
        rows[0]["relative_path"] = f"../{rows[0]['filename']}"
    elif problem == "absolute":
        rows[0]["relative_path"] = str((raw / rows[0]["filename"]).resolve())
    else:
        rows[1].update({key: rows[0][key] for key in ("filename", "relative_path", "bytes", "sha256")})
    write_manifest(manifest, rows)

    with pytest.raises(ValueError):
        reproducer.verify_sources(manifest)


def test_reserve_output_creates_fresh_directory_and_preserves_existing_content(tmp_path):
    fresh = tmp_path / "nested" / "replay"
    reproducer.reserve_output(fresh)
    assert fresh.is_dir()
    with pytest.raises(FileExistsError):
        reproducer.reserve_output(fresh)
    sentinel = fresh / "keep.txt"
    sentinel.write_bytes(b"previous output")

    with pytest.raises(FileExistsError):
        reproducer.reserve_output(fresh)

    assert sentinel.read_bytes() == b"previous output"
    assert list(fresh.iterdir()) == [sentinel]
