import copy
import importlib.util
from pathlib import Path

import numpy as np

SPEC = importlib.util.spec_from_file_location(
    "inspect_data", Path(__file__).resolve().parents[1] / "src" / "inspect_data.py"
)
inspection = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inspection)


def test_global_coordinates_are_cell_centers_in_source_order():
    lat, lon = inspection.grid_coordinates()

    assert lat.shape == (3600,)
    assert lon.shape == (7200,)
    np.testing.assert_allclose(lat[[0, -1]], [89.975, -89.975])
    np.testing.assert_allclose(lon[[0, -1]], [-179.975, 179.975])
    np.testing.assert_allclose(np.diff(lat), -0.05)
    np.testing.assert_allclose(np.diff(lon), 0.05)


def test_phoenix_window_contains_twelve_by_sixteen_cell_centers():
    lat, lon = inspection.grid_coordinates()
    phoenix_lat = lat[(lat >= 33.2) & (lat < 33.8)]
    phoenix_lon = lon[(lon >= -112.4) & (lon < -111.6)]

    assert phoenix_lat.shape == (12,)
    assert phoenix_lon.shape == (16,)
    np.testing.assert_allclose(phoenix_lat[[0, -1]], [33.775, 33.225])
    np.testing.assert_allclose(phoenix_lon[[0, -1]], [-112.375, -111.625])


def test_temperature_plot_masks_fill_and_range_without_changing_source():
    raw = np.array([0, 7499, 7500, 10000, 65535], dtype=np.uint16)
    attrs = {
        "_FillValue": 0,
        "valid_range": [7500, 65535],
        "scale_factor": 0.02,
        "add_offset": 0.0,
        "units": "K",
    }
    original_raw, original_attrs = raw.copy(), copy.deepcopy(attrs)

    kelvin = inspection.decode_for_plot(raw, attrs)

    np.testing.assert_allclose(kelvin, [np.nan, np.nan, 150.0, 200.0, 1310.7], equal_nan=True)
    np.testing.assert_array_equal(raw, original_raw)
    assert raw.dtype == np.uint16
    assert attrs == original_attrs


def test_temperature_plot_applies_scale_then_offset_once():
    raw = np.array([7500, 10000], dtype=np.uint16)
    attrs = {
        "_FillValue": 0,
        "valid_range": [7500, 65535],
        "scale_factor": 0.02,
        "add_offset": 1.5,
        "units": "K",
    }

    np.testing.assert_allclose(inspection.decode_for_plot(raw, attrs), [151.5, 201.5])
