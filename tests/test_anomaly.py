"""Monthly baselines, retained missing values and anomaly CSV compatibility."""

import numpy as np
import pandas as pd
import pytest

from earth_system_trend.aggregate import save_series
from earth_system_trend.anomaly import monthly_anomalies
from earth_system_trend.timeseries import load_timeseries


def seasonal_series(offsets):
    dates = pd.date_range("2003-01-01", periods=12 * len(offsets), freq="MS")
    seasonal = np.tile(5.0 + 2.0 * np.arange(1, 13), len(offsets))
    return pd.DataFrame({
        "date": dates.strftime("%Y-%m"),
        "value": seasonal + np.repeat(offsets, 12),
    })


def test_calendar_month_baseline_removes_seasons_and_sorts_without_mutation():
    source = seasonal_series([-1.0, 1.0]).iloc[::-1].copy()
    original = source.copy(deep=True)

    anomalies, climatology = monthly_anomalies(source)

    assert list(anomalies.columns) == ["date", "value"]
    assert anomalies.date.tolist() == seasonal_series([-1.0, 1.0]).date.tolist()
    np.testing.assert_allclose(anomalies.value, np.repeat([-1.0, 1.0], 12))
    assert list(climatology.columns) == ["month", "mean", "count"]
    assert climatology.month.tolist() == list(range(1, 13))
    np.testing.assert_allclose(climatology["mean"], 5.0 + 2.0 * np.arange(1, 13))
    np.testing.assert_array_equal(climatology["count"], np.repeat(2, 12))
    for month in range(12):
        assert anomalies.value.iloc[month::12].mean() == pytest.approx(0.0)
    pd.testing.assert_frame_equal(source, original)


def test_explicit_baseline_excludes_later_values_without_removing_their_offset():
    source = seasonal_series([-1.0, 1.0, 100.0])

    anomalies, climatology = monthly_anomalies(source, "2003-01", "2004-12")

    np.testing.assert_allclose(climatology["mean"], 5.0 + 2.0 * np.arange(1, 13))
    np.testing.assert_array_equal(climatology["count"], np.repeat(2, 12))
    np.testing.assert_allclose(anomalies.value, np.repeat([-1.0, 1.0, 100.0], 12))


def test_missing_baseline_values_are_excluded_from_mean_and_count():
    source = seasonal_series([-1.0, 1.0, 3.0])
    source.loc[source.date == "2004-03", "value"] = np.nan

    anomalies, climatology = monthly_anomalies(source)

    march = climatology.loc[climatology.month == 3].iloc[0]
    assert march["count"] == 2
    assert march["mean"] == pytest.approx(12.0)
    np.testing.assert_allclose(
        anomalies.loc[anomalies.date.str.endswith("-03"), "value"],
        [-2.0, np.nan, 2.0], equal_nan=True,
    )


def test_insufficient_baseline_months_keep_blank_rows_and_backend_nulls(tmp_path):
    source = seasonal_series([-1.0, 1.0])
    source.loc[source.date == "2003-01", "value"] = np.nan
    source.loc[source.date.str.endswith("-02"), "value"] = np.nan
    anomalies, climatology = monthly_anomalies(source)
    target = tmp_path / "anomaly.csv"

    save_series(anomalies, target)

    assert len(anomalies) == 24
    january = climatology.loc[climatology.month == 1].iloc[0]
    february = climatology.loc[climatology.month == 2].iloc[0]
    assert january["count"] == 1 and pd.isna(january["mean"])
    assert february["count"] == 0 and pd.isna(february["mean"])
    content = target.read_bytes()
    assert b"2003-01,\n" in content and b"2004-01,\n" in content
    assert b"2003-02,\n" in content and b"2004-02,\n" in content
    assert b"nan" not in content.lower()
    points = load_timeseries(target)
    assert len(points) == 24
    assert all(points[index].value is None for index in (0, 1, 12, 13))
    assert points[2].value == pytest.approx(-1.0)
    assert points[14].value == pytest.approx(1.0)


@pytest.mark.parametrize("problem", ["duplicate", "gap"])
def test_duplicate_or_missing_month_coordinates_are_rejected(problem):
    source = seasonal_series([-1.0, 1.0])
    if problem == "duplicate":
        source.loc[0, "date"] = source.loc[1, "date"]
    else:
        source = source.drop(index=1)

    with pytest.raises(ValueError):
        monthly_anomalies(source)


@pytest.mark.parametrize(
    ("start", "end"),
    [("2004-12", "2003-01"), ("1990-01", "1999-12")],
)
def test_reversed_or_nonoverlapping_baseline_is_rejected(start, end):
    with pytest.raises(ValueError):
        monthly_anomalies(seasonal_series([-1.0, 1.0]), start, end)
