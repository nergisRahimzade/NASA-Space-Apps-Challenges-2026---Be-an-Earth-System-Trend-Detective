"""Keep the complete monthly record when preparing a small per-cell timing trial."""

import numpy as np
import pytest
import xarray as xr

from earth_system_trend import chunk_check
from earth_system_trend.trend import TrendError


@pytest.fixture
def dataset():
    months = np.arange("2003-01", "2005-01", dtype="datetime64[M]")
    values = np.arange(24 * 6 * 8, dtype=float).reshape(24, 6, 8)
    return xr.Dataset(
        {"lst_night": (("time", "lat", "lon"), values, {"units": "degC"})},
        coords={"time": months, "lat": 33.775 - np.arange(6) * 0.05,
                "lon": -112.375 + np.arange(8) * 0.05},
    )


def test_chunk_sizes_keep_time_whole_and_cap_spatial_edges_without_mutation():
    values = np.arange(24 * 55 * 52, dtype=float).reshape(24, 55, 52)
    values[3, 51, 51] = np.nan
    source = xr.Dataset(
        {"lst_night": (("lon", "time", "lat"), values.transpose(2, 0, 1), {"units": "degC"})},
        coords={"time": np.arange("2003-01", "2005-01", dtype="datetime64[M]"),
                "lat": np.arange(55), "lon": np.arange(52)},
    )
    original = source.copy(deep=True)

    chunked = chunk_check.chunk_nighttime(source)

    assert chunked.dims == ("time", "lat", "lon")
    assert chunked.chunks == ((24,), (50, 5), (50, 2))
    xr.testing.assert_identical(chunked.compute(), source.lst_night.transpose("time", "lat", "lon"))
    xr.testing.assert_identical(source, original)
    assert source.lst_night.chunks is None


@pytest.mark.parametrize("problem", ["units", "dimensions", "gap", "duplicate", "short", "reverse"])
def test_invalid_units_dimensions_or_monthly_calendar_are_rejected(dataset, problem):
    if problem == "units":
        dataset.lst_night.attrs["units"] = "K"
    elif problem == "dimensions":
        dataset = dataset.rename({"lon": "x"})
    elif problem == "gap":
        dates = dataset.time.values.astype("datetime64[M]").copy()
        dates[12:] = dates[12:] + np.timedelta64(1, "M")
        dataset = dataset.assign_coords(time=dates)
    elif problem == "duplicate":
        dates = dataset.time.values.copy()
        dates[12] = dates[11]
        dataset = dataset.assign_coords(time=dates)
    elif problem == "short":
        dataset = dataset.isel(time=slice(0, 23))
    else:
        dataset = dataset.isel(time=slice(None, None, -1))

    with pytest.raises(ValueError):
        chunk_check.chunk_nighttime(dataset)


def test_centered_trial_passes_complete_cell_values_and_dates_to_existing_function(dataset, monkeypatch):
    seen = []
    monkeypatch.setattr(chunk_check, "run_trend", lambda points: seen.append(points))

    report = chunk_check.benchmark_cells(chunk_check.chunk_nighttime(dataset), budget_seconds=1e6)

    assert report["sample"]["lat_slice"] == [1, 5]
    assert report["sample"]["lon_slice"] == [2, 6]
    assert report["sample"]["cell_count"] == report["tested_cells"] == len(seen) == 16
    expected_dates = dataset.time.values.astype("datetime64[M]").astype(str).tolist()
    expected_values = [dataset.lst_night.values[:, i, j].tolist()
                       for i in range(1, 5) for j in range(2, 6)]
    assert [[point.value for point in points] for points in seen] == expected_values
    assert all([point.date for point in points] == expected_dates for points in seen)
    assert report["decision"] == "optional_per_cell_trial"
    assert report["incomplete_cells"] == report["failed_cells"] == 0
    assert "slopes" not in report and "trends" not in report


def test_missing_cell_is_skipped_but_complete_constant_cell_is_tested(dataset, monkeypatch):
    dataset.lst_night.values[8, 1, 2] = np.nan
    dataset.lst_night.values[:, 1, 3] = 7
    seen = []
    monkeypatch.setattr(chunk_check, "run_trend", lambda points: seen.append(points))

    report = chunk_check.benchmark_cells(chunk_check.chunk_nighttime(dataset), budget_seconds=1e6)

    assert report["incomplete_cells"] == 1
    assert report["tested_cells"] == len(seen) == 15
    assert report["decision"] == "retain_subregions"
    assert all(len(points) == 24 and all(point.value is not None for point in points) for points in seen)
    assert any(all(point.value == 7 for point in points) for points in seen)


def test_failed_trend_calls_keep_subregions_and_cannot_supply_a_runtime_estimate(dataset, monkeypatch):
    def fail(points):
        raise TrendError("No usable test result")

    monkeypatch.setattr(chunk_check, "run_trend", fail)

    report = chunk_check.benchmark_cells(chunk_check.chunk_nighttime(dataset))

    assert report["tested_cells"] == 0
    assert report["failed_cells"] == 16
    assert report["estimated_full_window_seconds"] is None
    assert report["decision"] == "retain_subregions"


def test_full_window_projection_counts_loading_once_and_enforces_budget(dataset, monkeypatch):
    ticks = iter([0.0, 2.0, 2.0, 18.0])
    monkeypatch.setattr(chunk_check, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(chunk_check, "run_trend", lambda points: None)

    report = chunk_check.benchmark_cells(chunk_check.chunk_nighttime(dataset), budget_seconds=30.0)

    assert report["load_seconds"] == 2.0
    assert report["trend_seconds"] == 16.0
    assert report["estimated_full_window_seconds"] == 50.0  # 2 + (16 / 16) * 48
    assert report["decision"] == "retain_subregions"
