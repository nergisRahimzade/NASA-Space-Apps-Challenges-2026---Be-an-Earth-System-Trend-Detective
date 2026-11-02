import importlib.util
from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from inspect_data import XDIM, YDIM

SPEC = importlib.util.spec_from_file_location(
    "clean_data", Path(__file__).resolve().parents[1] / "src" / "clean_data.py"
)
cleaner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleaner)

RENAMED = {
    "LST_Day_CMG": "lst_day", "LST_Night_CMG": "lst_night",
    "QC_Day": "qc_day", "QC_Night": "qc_night",
    "Day_view_time": "day_view_time", "Night_view_time": "night_view_time",
    "Day_view_angl": "day_view_angle", "Night_view_angl": "night_view_angle",
    "Clear_sky_days": "clear_sky_days", "Clear_sky_nights": "clear_sky_nights",
    **{f"Emis_{band}": f"emissivity_{band}" for band in (20, 22, 23, 29, 31, 32)},
    "Percent_land_in_grid": "percent_land",
}


@pytest.fixture
def raw_dataset(monkeypatch):
    lat = np.array([34.1, 33.775, 33.225, 33.0])
    lon = np.array([-112.6, -112.375, -112.125, -111.875, -111.625, -111.4])
    monkeypatch.setattr(cleaner, "grid_coordinates", lambda *args, **kwargs: (lat, lon))

    def field(values, dtype, attrs):
        raw = np.zeros((1, 4, 6), dtype=dtype)
        raw[0, 1:3, 1:5] = values
        return xr.DataArray(raw, dims=("time", YDIM, XDIM), attrs=attrs)

    fields = {}
    for period in ("Day", "Night"):
        fields[f"LST_{period}_CMG"] = field(
            [[0, 7499, 7500, 65535], [15000, 10000, 20000, 16000]], np.uint16,
            {"units": "K", "valid_range": [7500, 65535], "_FillValue": 0,
             "scale_factor": 0.02, "add_offset": 0.0},
        )
        fields[f"QC_{period}"] = field(
            [[0, 1, 2, 255], [3, 64, 128, 255]], np.uint8,
            {"valid_range": [0, 255], "_FillValue": b"NA\x00"},
        )
        fields[f"{period}_view_time"] = field(
            [[0, 120, 121, 255], [24, 25, 60, 100]], np.uint8,
            {"units": "hrs", "valid_range": [0, 120], "_FillValue": 255,
             "scale_factor": 0.2, "add_offset": 0.0},
        )
        fields[f"{period}_view_angl"] = field(
            [[0, 65, 130, 131], [255, 57, 67, 100]], np.uint8,
            {"units": "deg", "valid_range": [0, 130], "_FillValue": 255,
             "scale_factor": 1.0, "add_offset": -65.0},
        )
    for name in ("Clear_sky_days", "Clear_sky_nights"):
        fields[name] = field(
            [[0, 1, 2**31, 2**32 - 1], [2**30, 3, 5, 7]], np.uint32,
            {"valid_range": [0, 2**32 - 1], "_FillValue": b"NA\x00"},
        )
    for band in (20, 22, 23, 29, 31, 32):
        fields[f"Emis_{band}"] = field(
            [[0, 1, 255, 128], [250, 251, 252, 253]], np.uint8,
            {"valid_range": [1, 255], "_FillValue": 0,
             "scale_factor": 0.002, "add_offset": 0.49},
        )
    fields["Percent_land_in_grid"] = field(
        [[0, 1, 100, 101], [100, 75, 50, 25]], np.uint8,
        {"valid_range": [1, 100], "_FillValue": 0},
    )
    return xr.Dataset(
        fields, coords={"time": np.array(["2003-01-01"], dtype="datetime64[ns]")},
        attrs={"StructMetadata.0": "original global grid"},
    )


def test_cleaning_renames_all_fields_and_selects_phoenix_without_mutation(raw_dataset):
    original = raw_dataset.copy(deep=True)

    cleaned = cleaner.clean_dataset(raw_dataset)

    assert set(cleaned.data_vars) == set(RENAMED.values())
    assert dict(cleaned.sizes) == {"time": 1, "lat": 2, "lon": 4}
    np.testing.assert_allclose(cleaned.lat, [33.775, 33.225])
    np.testing.assert_allclose(cleaned.lon, [-112.375, -112.125, -111.875, -111.625])
    np.testing.assert_array_equal(cleaned.time, original.time)
    assert "StructMetadata.0" not in cleaned.attrs
    xr.testing.assert_identical(raw_dataset, original)


def test_lst_fill_range_and_celsius_conversion(raw_dataset):
    cleaned = cleaner.clean_dataset(raw_dataset)

    expected = [[np.nan, np.nan, -123.15, 1037.55], [26.85, -73.15, 126.85, 46.85]]
    for name in ("lst_day", "lst_night"):
        np.testing.assert_allclose(cleaned[name].values[0], expected, atol=2e-5, equal_nan=True)
        assert cleaned[name].attrs["units"] == "degC"


def test_observation_times_angles_emissivity_and_land_are_decoded(raw_dataset):
    cleaned = cleaner.clean_dataset(raw_dataset)

    for period in ("day", "night"):
        np.testing.assert_allclose(
            cleaned[f"{period}_view_time"].values[0, 0], [0, 24, np.nan, np.nan], equal_nan=True,
        )
        np.testing.assert_allclose(
            cleaned[f"{period}_view_angle"].values[0],
            [[-65, 0, 65, np.nan], [np.nan, -8, 2, 35]], equal_nan=True,
        )
    for band in (20, 22, 23, 29, 31, 32):
        np.testing.assert_allclose(
            cleaned[f"emissivity_{band}"].values[0, 0],
            [np.nan, 0.492, 1.0, 0.746], atol=1e-7, equal_nan=True,
        )
    np.testing.assert_allclose(
        cleaned.percent_land.values[0, 0], [np.nan, 1, 100, np.nan], equal_nan=True,
    )


def test_qc_and_bitmaps_keep_zero_and_high_bits_without_extra_quality_filter(raw_dataset):
    cleaned = cleaner.clean_dataset(raw_dataset)

    for old, new in (("QC_Day", "qc_day"), ("QC_Night", "qc_night"),
                     ("Clear_sky_days", "clear_sky_days"), ("Clear_sky_nights", "clear_sky_nights")):
        assert cleaned[new].dtype == raw_dataset[old].dtype
        np.testing.assert_array_equal(cleaned[new], raw_dataset[old].values[:, 1:3, 1:5])
    # A produced but nonzero QC flag does not invent an unapproved screening rule.
    assert cleaned.qc_night.values[0, 1, 0] == 3
    assert cleaned.lst_night.values[0, 1, 0] == pytest.approx(26.85, abs=2e-5)


def test_decoded_fields_do_not_advertise_packed_scaling_again(raw_dataset):
    cleaned = cleaner.clean_dataset(raw_dataset)

    flags = {"qc_day", "qc_night", "clear_sky_days", "clear_sky_nights"}
    for name in set(cleaned.data_vars) - flags:
        for key in ("scale_factor", "add_offset", "_FillValue", "valid_range"):
            assert key not in cleaned[name].attrs


def test_clean_netcdf_reopens_with_same_values_types_and_no_double_decoding(raw_dataset, tmp_path):
    cleaned = cleaner.clean_dataset(raw_dataset)
    target = tmp_path / "clean.nc"

    cleaner.save_clean_dataset(cleaned, target)

    with xr.open_dataset(target, engine="netcdf4") as reopened:
        assert set(reopened.data_vars) == set(RENAMED.values())
        np.testing.assert_array_equal(reopened.time, cleaned.time)
        np.testing.assert_allclose(reopened.lat, cleaned.lat)
        np.testing.assert_allclose(reopened.lon, cleaned.lon)
        for name in cleaned.data_vars:
            np.testing.assert_allclose(reopened[name], cleaned[name], equal_nan=True)
        assert reopened.qc_night.dtype == np.uint8
        assert reopened.clear_sky_nights.dtype == np.uint32
        assert reopened.qc_night.values[0, 0, 0] == 0
        assert reopened.clear_sky_nights.values[0, 0, 2] == 2**31
        assert reopened.lst_night.values[0, 1, 0] == pytest.approx(26.85, abs=2e-5)
        for name in ("day_view_time", "night_view_time"):
            assert np.issubdtype(reopened[name].dtype, np.floating)
            assert reopened[name].attrs["units"] == "hrs"
            assert reopened[name].attrs["time_reference"] == "UTC"
