"""Read the Data layer's monthly CSV into the contract's series format.

ESD-D08-BE. The CSV needs two columns, `date` and `value`:

    date,value
    2003-01,13.2
    2003-02,
    2003-03,17.5

- `date` is YYYY-MM (a full date such as 2003-01-15 is cut to its month).
- An empty value, or NaN, means the month is missing and becomes null.
- Months left out of the file entirely are filled in as null, so the series
  always has one entry per month from the first to the last, as the contract
  requires.
"""

from __future__ import annotations

import csv
import math
import re
from pathlib import Path

from .contract import SeriesPoint

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class TimeseriesError(ValueError):
    """The CSV is missing or not in the expected date,value format."""


def next_month(month: str) -> str:
    """'2003-12' -> '2004-01'."""
    year, mon = int(month[:4]), int(month[5:7])
    return f"{year + 1}-01" if mon == 12 else f"{year}-{mon + 1:02d}"


def load_timeseries(path: str | Path) -> list[SeriesPoint]:
    """Return one SeriesPoint per month, oldest first, from a date,value CSV."""
    path = Path(path)
    if not path.exists():
        raise TimeseriesError(f"{path}: file not found")

    values: dict[str, float | None] = {}
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not {"date", "value"} <= set(reader.fieldnames):
            raise TimeseriesError(f"{path}: needs 'date' and 'value' columns")
        for line_number, row in enumerate(reader, start=2):  # line 1 is the header
            month = (row["date"] or "").strip()[:7]
            if not MONTH.match(month):
                raise TimeseriesError(f"{path} line {line_number}: bad date {row['date']!r}")
            if month in values:
                raise TimeseriesError(f"{path} line {line_number}: {month} appears twice")
            values[month] = _parse_value(row["value"], path, line_number)

    if not values:
        raise TimeseriesError(f"{path}: no rows")

    series, month, last = [], min(values), max(values)
    while month <= last:
        series.append(SeriesPoint(date=month, value=values.get(month)))
        month = next_month(month)
    return series


def _parse_value(text: str | None, path: Path, line_number: int) -> float | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError as exc:
        raise TimeseriesError(f"{path} line {line_number}: bad value {text!r}") from exc
    return None if math.isnan(value) else value
