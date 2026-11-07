"""Per-cell calendar safety, lazy mapping and the NetCDF handoff."""

import hashlib
import json

import numpy as np
import pytest
import xarray as xr

from earth_system_trend import trend_map
from earth_system_trend.trend import TrendError


def monthly_dates(months=264):
    return np.arange(np.datetime64("2003-01", "M"),
                     np.datetime64("2003-01", "M") + np.timedelta64(months, "M")).astype(str).tolist()


@pytest.fixture
def dataset():
    t = np.arange(264, dtype=float)
    values = np.stack([t / 10, -t / 10, np.full(264, 7.0),
                       t / 5, t, -t], axis=1).reshape(264, 2, 3)
    values[100, 1, 0] = np.nan
    return xr.Dataset(
        {"lst_night": (("time", "lat", "lon"), values, {"units": "degC"})},
        coords={"time": np.asarray(monthly_dates(), dtype="datetime64[M]"),
                "lat": [33.575, 33.525], "lon": [-112.075, -112.025, -111.975]},
        attrs={"quality_policy": "Numeric fill and valid range only; production QC filter not applied"},
    )


def test_known_monthly_slopes_and_constant_series_use_existing_test():
    dates = monthly_dates()
    t = np.arange(len(dates), dtype=float)
    for values, slope, tau, direction in ((t / 10, 0.1, 1, 1), (-t / 10, -0.1, -1, -1),
                                           (np.full(len(dates), 7.0), 0, 0, 0)):
        actual_slope, p, actual_tau, actual_direction, count, status = trend_map.cell_statistics(values, dates)
        assert actual_slope == pytest.approx(slope)
        assert actual_tau == tau
        assert actual_direction == direction
        assert count == 264 and status == 0
        if direction == 0:
            assert p == 1
        else:
            assert p < 0.05


def test_missing_endpoint_or_internal_month_is_flagged_without_compressing_calendar():
    dates = monthly_dates()
    for index, bad in ((0, np.nan), (100, np.nan), (263, np.nan), (100, np.inf)):
        values = np.arange(264, dtype=float)
        values[index] = bad
        slope, p, tau, direction, count, status = trend_map.cell_statistics(values, dates)
        assert np.isnan([slope, p, tau]).all()
        assert direction == 2 and count == 263 and status == 1
    short = trend_map.cell_statistics(np.arange(23, dtype=float), monthly_dates(23))
    assert np.isnan(short[:3]).all()
    assert short[3:] == (2, 23, 2)


def test_failed_trend_is_flagged_without_fabricated_numbers(monkeypatch):
    def fail(series):
        raise TrendError("No usable result")

    monkeypatch.setattr(trend_map, "run_trend", fail)
    slope, p, tau, direction, count, status = trend_map.cell_statistics(np.arange(264), monthly_dates())
    assert np.isnan([slope, p, tau]).all()
    assert direction == 2 and count == 264 and status == 3


def test_lazy_map_preserves_coordinate_order_and_transposed_source(dataset):
    for reverse_lat, reverse_lon in ((False, False), (True, False), (False, True), (True, True)):
        source = dataset.isel(lat=slice(None, None, -1) if reverse_lat else slice(None),
                              lon=slice(None, None, -1) if reverse_lon else slice(None))
        source = source.transpose("lon", "time", "lat")
        original = source.copy(deep=True)

        result = trend_map.make_trend_map(source)

        assert set(result.data_vars) == {"slope", "p", "tau", "direction", "n_valid", "status"}
        assert all(result[name].chunks is not None for name in result.data_vars)
        np.testing.assert_array_equal(result.lat, source.lat)
        np.testing.assert_array_equal(result.lon, source.lon)
        loaded = result.compute(scheduler="single-threaded")
        increasing = loaded.sel(lat=33.575, lon=-112.075)
        assert increasing.slope.item() == pytest.approx(0.1)
        assert increasing.direction.item() == 1 and increasing.status.item() == 0
        missing = loaded.sel(lat=33.525, lon=-112.075)
        assert np.isnan(missing.slope.item()) and missing.status.item() == 1
        assert missing.n_valid.item() == 263
        xr.testing.assert_identical(source, original)


def test_invalid_time_axis_is_rejected_before_creating_a_map(dataset):
    dates = dataset.time.values.astype("datetime64[M]").copy()
    dates[100] = dates[99]
    with pytest.raises(ValueError):
        trend_map.make_trend_map(dataset.assign_coords(time=dates))
    with pytest.raises(ValueError):
        trend_map.make_trend_map(dataset.isel(time=slice(None, None, -1)))


def test_atomic_netcdf_roundtrip_keeps_nan_flags_types_and_existing_file_on_failure(dataset, tmp_path, monkeypatch):
    result = trend_map.make_trend_map(dataset).compute(scheduler="single-threaded")
    target = tmp_path / "trend_map.nc"

    trend_map.save_trend_map(result, target)

    with xr.open_dataset(target) as reopened:
        xr.testing.assert_identical(reopened, result)
        assert reopened.direction.dtype == np.int8
        assert reopened.status.dtype == np.int8
        assert reopened.n_valid.dtype == np.int16
        assert reopened.status.sel(lat=33.525, lon=-112.075).item() == 1
        assert np.isnan(reopened.slope.sel(lat=33.525, lon=-112.075).item())
        assert all(reopened[name].encoding.get("_FillValue") is None
                   for name in ("direction", "n_valid", "status"))
    before = target.read_bytes()

    def fail_write(*args, **kwargs):
        raise OSError("Simulated interrupted write")

    monkeypatch.setattr(xr.Dataset, "to_netcdf", fail_write)
    with pytest.raises(OSError, match="interrupted"):
        trend_map.save_trend_map(result, target)
    assert target.read_bytes() == before
    assert set(tmp_path.iterdir()) == {target}


@pytest.mark.parametrize("ticks,expected_calls", [([0.0, 31.0], 1), ([0.0, 1.0, 1.0, 32.0], 2)],
                         ids=["slow-sample", "slow-full-window"])
def test_cli_skips_save_and_preview_when_trial_exceeds_budget(tmp_path, monkeypatch, ticks, expected_calls):
    source = xr.Dataset(
        {"lst_night": (("time", "lat", "lon"),
                       np.arange(264, dtype=float)[:, None, None] / 10 + np.zeros((264, 6, 8)),
                       {"units": "degC"})},
        coords={"time": np.asarray(monthly_dates(), dtype="datetime64[M]"),
                "lat": 33.775 - np.arange(6) * 0.05,
                "lon": -112.375 + np.arange(8) * 0.05},
        attrs={"quality_policy": "Numeric fill and valid range only; production QC filter not applied"},
    )
    input_path = tmp_path / "clean.nc"
    source.to_netcdf(input_path, engine="netcdf4")
    prior = tmp_path / "docs/evidence/day12/chunk_check.json"
    prior.parent.mkdir(parents=True)
    prior.write_text(json.dumps({"source_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest()}))
    output_path = tmp_path / "trend_map.nc"
    previous_output = b"previously generated map"
    output_path.write_bytes(previous_output)
    evidence = tmp_path / "evidence"
    calls = []
    original_make_map = trend_map.make_trend_map

    def record_map(dataset):
        calls.append(dict(dataset.sizes))
        return original_make_map(dataset)

    def unexpected_output(*args, **kwargs):
        pytest.fail("An over-budget trial must not save a map or preview")

    ticks = iter(ticks)
    monkeypatch.setattr(trend_map, "perf_counter", lambda: next(ticks))
    monkeypatch.setattr(trend_map, "make_trend_map", record_map)
    monkeypatch.setattr(trend_map, "save_trend_map", unexpected_output)
    monkeypatch.setattr(trend_map, "plot_map", unexpected_output)
    monkeypatch.chdir(tmp_path)

    assert trend_map.main(["--input", str(input_path), "--output", str(output_path),
                           "--evidence", str(evidence)]) == 0

    report = json.loads((evidence / "trend_map_check.json").read_text())
    assert report["status"] == "skipped"
    assert report["budget_seconds"] == 30.0
    if expected_calls == 1:
        assert report["sample_seconds"] == 31.0
        assert "full_window_seconds" not in report
        assert calls == [{"time": 264, "lat": 4, "lon": 4}]
    else:
        assert report["sample_seconds"] == 1.0 and report["full_window_seconds"] == 31.0
        assert calls == [{"time": 264, "lat": 4, "lon": 4}, {"time": 264, "lat": 6, "lon": 8}]
    assert output_path.read_bytes() == previous_output
    assert not (evidence / "trend_map.png").exists()
