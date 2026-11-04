"""Area weighting, missing-month handling and the Data-to-Backend CSV handoff."""

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from earth_system_trend.aggregate import monthly_series, save_series
from earth_system_trend.timeseries import load_timeseries


@pytest.fixture
def clean_dataset():
    values = np.array([
        [[0.0, 10.0], [20.0, 30.0]],
        [[10.0, 20.0], [30.0, 40.0]],
        [[20.0, 30.0], [40.0, 50.0]],
    ])
    return xr.Dataset(
        {
            "lst_night": (("time", "lat", "lon"), values, {"units": "degC"}),
            # These flags and counts must not introduce an unrequested weighting rule.
            "qc_night": (("time", "lat", "lon"), np.full(values.shape, 3, dtype=np.uint8)),
            "clear_sky_nights": (("time", "lat", "lon"),
                                 np.broadcast_to([[31, 1], [3, 7]], values.shape).astype(np.uint32)),
        },
        coords={
            "time": np.array(["2003-01-01", "2003-02-01", "2003-03-01"], dtype="datetime64[ns]"),
            "lat": ("lat", [0.0, 60.0], {"units": "degrees_north"}),
            "lon": ("lon", [-112.1, -112.0], {"units": "degrees_east"}),
        },
        attrs={"quality_policy": "Numeric fill and valid range only"},
    )


def test_cosine_weights_use_degrees_and_broadcast_across_longitude_without_mutation(clean_dataset):
    original = clean_dataset.copy(deep=True)

    result = monthly_series(clean_dataset)

    assert list(result.columns) == ["date", "value"]
    assert result.date.tolist() == ["2003-01", "2003-02", "2003-03"]
    # Latitude 0 and 60 degrees have weights 1 and 1/2, for both longitude cells.
    np.testing.assert_allclose(result.value, [35 / 3, 65 / 3, 95 / 3], rtol=1e-12)
    xr.testing.assert_identical(clean_dataset, original)


def test_missing_cells_are_removed_from_the_weight_denominator(clean_dataset):
    clean_dataset.lst_night.values[0] = [[0.0, np.nan], [20.0, 40.0]]

    result = monthly_series(clean_dataset)

    # (0*1 + 20*.5 + 40*.5) / (1 + .5 + .5), not divided by the full-grid weight 3.
    assert result.value.iloc[0] == pytest.approx(15.0)


def test_all_missing_month_remains_a_blank_csv_row_and_backend_null(clean_dataset, tmp_path):
    clean_dataset.lst_night.values[1] = np.nan
    result = monthly_series(clean_dataset)
    target = tmp_path / "timeseries.csv"

    save_series(result, target)

    content = target.read_bytes()
    assert content.startswith(b"date,value\n")
    assert b"2003-02,\n" in content
    assert b"\r" not in content
    assert b"nan" not in content.lower()
    points = load_timeseries(target)
    assert [point.date for point in points] == ["2003-01", "2003-02", "2003-03"]
    assert points[1].value is None
    assert points[0].value == pytest.approx(35 / 3)
    assert points[2].value == pytest.approx(95 / 3)


def test_reversed_input_is_sorted_by_month(clean_dataset):
    result = monthly_series(clean_dataset.isel(time=[2, 1, 0]))

    assert result.date.tolist() == ["2003-01", "2003-02", "2003-03"]
    np.testing.assert_allclose(result.value, [35 / 3, 65 / 3, 95 / 3], rtol=1e-12)


@pytest.mark.parametrize(
    ("dates", "message"),
    [
        (["2003-01-01", "2003-01-31", "2003-03-01"], "Duplicate"),
        (["2003-01-01", "2003-03-01", "2003-04-01"], "missing"),
    ],
)
def test_duplicate_or_missing_months_are_rejected(clean_dataset, dates, message):
    dataset = clean_dataset.assign_coords(time=np.array(dates, dtype="datetime64[ns]"))

    with pytest.raises(ValueError, match=message):
        monthly_series(dataset)


def test_kelvin_input_is_rejected_instead_of_mislabeled_as_celsius(clean_dataset):
    clean_dataset.lst_night.attrs["units"] = "K"

    with pytest.raises(ValueError):
        monthly_series(clean_dataset)


def test_csv_keeps_float_precision_for_existing_backend_reader(tmp_path):
    values = [7.7619053003732565, -4.123456789012345]
    frame = pd.DataFrame({"date": ["2003-01", "2003-02"], "value": values})
    target = tmp_path / "nested" / "timeseries.csv"

    save_series(frame, target)

    assert [point.value for point in load_timeseries(target)] == values
