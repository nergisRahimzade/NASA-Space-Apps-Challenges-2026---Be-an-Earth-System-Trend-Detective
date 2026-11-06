"""Geographic partitioning and monthly CSVs for the four Phoenix windows."""

import copy
import math

import numpy as np
import pytest
import xarray as xr

from earth_system_trend.aggregate import save_series
from earth_system_trend.subregions import regional_series, select_region
from earth_system_trend.timeseries import load_timeseries


@pytest.fixture
def definitions():
    return {
        "phoenix_northwest": {"label": "Phoenix northwest", "bounds": [-112.4, 33.5, -112.0, 33.8]},
        "phoenix_northeast": {"label": "Phoenix northeast", "bounds": [-112.0, 33.5, -111.6, 33.8]},
        "phoenix_southwest": {"label": "Phoenix southwest", "bounds": [-112.4, 33.2, -112.0, 33.5]},
        "phoenix_southeast": {"label": "Phoenix southeast", "bounds": [-112.0, 33.2, -111.6, 33.5]},
    }


@pytest.fixture
def clean_dataset():
    first = np.arange(16, dtype=float).reshape(4, 4)
    values = np.stack([first, first + 1])
    return xr.Dataset(
        {
            "lst_night": (("time", "lat", "lon"), values, {"units": "degC"}),
            "qc_night": (("time", "lat", "lon"), np.full(values.shape, 3, dtype=np.uint8)),
        },
        coords={
            "time": np.array(["2003-01-01", "2003-02-01"], dtype="datetime64[ns]"),
            "lat": [33.725, 33.575, 33.425, 33.275],
            "lon": [-112.325, -112.125, -111.925, -111.725],
        },
        attrs={"quality_policy": "Numeric fill and valid range only"},
    )


def test_four_series_use_geographic_cells_and_cosine_weights_without_mutation(clean_dataset, definitions):
    original = clean_dataset.copy(deep=True)

    series = regional_series(clean_dataset, definitions)

    assert set(series) == set(definitions)
    indices = {
        "phoenix_northwest": ((0, 1), (0, 1)),
        "phoenix_northeast": ((0, 1), (2, 3)),
        "phoenix_southwest": ((2, 3), (0, 1)),
        "phoenix_southeast": ((2, 3), (2, 3)),
    }
    for name, (rows, cols) in indices.items():
        weights = [math.cos(math.radians(float(original.lat[i]))) for i in rows for _ in cols]
        weighted = [float(original.lst_night.values[0, i, j]) * w
                    for (i, j), w in zip([(i, j) for i in rows for j in cols], weights)]
        expected = math.fsum(weighted) / math.fsum(weights)
        assert list(series[name].columns) == ["date", "value"]
        assert series[name].date.tolist() == ["2003-01", "2003-02"]
        np.testing.assert_allclose(series[name].value, [expected, expected + 1], atol=1e-12)
    xr.testing.assert_identical(clean_dataset, original)


def test_cells_on_split_boundaries_belong_to_exactly_one_region(clean_dataset, definitions):
    source = clean_dataset.assign_coords(
        lat=[33.725, 33.5, 33.425, 33.275], lon=[-112.325, -112.0, -111.925, -111.725]
    )
    selected = []
    for definition in definitions.values():
        region = select_region(source, definition["bounds"])
        selected.extend(region.lst_night.isel(time=0).values.ravel().tolist())

    assert sorted(selected) == list(range(16))
    northeast = select_region(source, definitions["phoenix_northeast"]["bounds"])
    assert northeast.lst_night.sel(lat=33.5, lon=-112.0).isel(time=0).item() == 5
    assert set(regional_series(source, definitions)) == set(definitions)


def test_real_study_grid_has_six_by_eight_cells_per_quadrant(definitions):
    source = xr.Dataset(
        {"lst_night": (("time", "lat", "lon"), np.full((2, 12, 16), 10.0), {"units": "degC"})},
        coords={
            "time": np.array(["2003-01-01", "2003-02-01"], dtype="datetime64[ns]"),
            "lat": 33.775 - np.arange(12) * 0.05,
            "lon": -112.375 + np.arange(16) * 0.05,
        },
    )
    for definition in definitions.values():
        selected = select_region(source, definition["bounds"])
        assert selected.sizes["lat"] == 6
        assert selected.sizes["lon"] == 8
    for frame in regional_series(source, definitions).values():
        np.testing.assert_allclose(frame.value, [10.0, 10.0])


def test_missing_cells_change_denominator_and_empty_month_stays_blank(clean_dataset, definitions, tmp_path):
    clean_dataset.lst_night.values[0, 0, 1] = np.nan
    clean_dataset.lst_night.values[1, :2, :2] = np.nan

    frame = regional_series(clean_dataset, definitions)["phoenix_northwest"]
    target = tmp_path / "timeseries_phoenix_northwest.csv"
    save_series(frame, target)

    north = math.cos(math.radians(33.725))
    south = math.cos(math.radians(33.575))
    expected = (0 * north + 4 * south + 5 * south) / (north + 2 * south)
    assert frame.value.iloc[0] == pytest.approx(expected, abs=1e-12)
    assert np.isnan(frame.value.iloc[1])
    assert b"2003-02,\n" in target.read_bytes()
    points = load_timeseries(target)
    assert points[0].value == pytest.approx(expected, abs=1e-12)
    assert points[1].value is None


def test_invalid_or_empty_boxes_are_rejected(clean_dataset):
    boxes = (
        [-112.0, 33.2, -112.0, 33.8],
        [-112.4, 33.8, -111.6, 33.2],
        [-110.0, 33.2, -109.0, 33.8],
        [np.nan, 33.2, -111.6, 33.8],
    )
    for bounds in boxes:
        with pytest.raises(ValueError):
            select_region(clean_dataset, bounds)


def test_overlapping_regions_are_rejected(clean_dataset, definitions):
    overlapping = copy.deepcopy(definitions)
    overlapping["phoenix_northwest"]["bounds"][2] = -111.6

    with pytest.raises(ValueError, match="(?i)overlap"):
        regional_series(clean_dataset, overlapping)


def test_regions_must_cover_all_source_cells(clean_dataset, definitions):
    incomplete = copy.deepcopy(definitions)
    incomplete["phoenix_northwest"]["bounds"][3] = 33.65

    with pytest.raises(ValueError, match="(?i)cover"):
        regional_series(clean_dataset, incomplete)


def test_region_count_accepts_three_to_five_only(clean_dataset, definitions):
    three = {
        "phoenix_west": {"label": "Phoenix west", "bounds": [-112.4, 33.2, -112.0, 33.8]},
        "phoenix_northeast": definitions["phoenix_northeast"],
        "phoenix_southeast": definitions["phoenix_southeast"],
    }
    five = {name: definition for name, definition in definitions.items() if name != "phoenix_northwest"}
    five.update({
        "phoenix_far_northwest": {"label": "Northwest west", "bounds": [-112.4, 33.5, -112.2, 33.8]},
        "phoenix_inner_northwest": {"label": "Northwest east", "bounds": [-112.2, 33.5, -112.0, 33.8]},
    })
    for valid in (three, five):
        assert set(regional_series(clean_dataset, valid)) == set(valid)
    too_few = dict(list(definitions.items())[:2])
    too_many = {**definitions, "extra_a": definitions["phoenix_northwest"],
                "extra_b": definitions["phoenix_northeast"]}
    for invalid in (too_few, too_many):
        with pytest.raises(ValueError):
            regional_series(clean_dataset, invalid)
