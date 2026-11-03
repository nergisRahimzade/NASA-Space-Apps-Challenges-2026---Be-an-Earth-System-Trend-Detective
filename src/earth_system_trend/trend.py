"""Stand-in trend test so the pipeline can run end to end.

ESD-D09-BE. The AI/ML layer owns the real run_trend (ticket ESD-D09-AI).
This version uses the same library and returns the contract's Trend shape,
so swapping theirs in later is a one-line import change in run.py.
"""

from __future__ import annotations

import math

import pymannkendall as mk

from .contract import SeriesPoint, Trend

MIN_VALUES = 24  # two years of months; fewer is too little to judge a trend


class TrendError(ValueError):
    """The series cannot be tested (too short, or no usable result)."""


def run_trend(series: list[SeriesPoint]) -> Trend:
    """Run the Mann-Kendall test on the months that have a value."""
    values = [point.value for point in series if point.value is not None]
    if len(values) < MIN_VALUES:
        raise TrendError(f"need at least {MIN_VALUES} months with values, got {len(values)}")

    result = mk.original_test(values)
    if math.isnan(result.p):
        raise TrendError("the trend test returned no p-value (is every value the same?)")
    return Trend(
        slope=round(float(result.slope), 4),
        p=round(float(result.p), 4),
        tau=round(float(result.Tau), 3),
        trend=result.trend,
    )
