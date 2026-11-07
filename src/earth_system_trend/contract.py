"""Pydantic model of the results contract (docs/contract.md) and a safe loader.

Usage:
    from earth_system_trend.contract import load_results, ContractError

    results = load_results("results.mock.json")   # raises ContractError if bad
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# pymannkendall returns exactly these strings in its `trend` field.
TrendDirection = Literal["increasing", "decreasing", "no trend"]


class _Strict(BaseModel):
    # Reject unknown fields so typos like "slpoe" fail loudly instead of being ignored.
    model_config = ConfigDict(extra="forbid")


class Period(_Strict):
    start: str = Field(pattern=r"^\d{4}-\d{2}$", description="First month, YYYY-MM")
    end: str = Field(pattern=r"^\d{4}-\d{2}$", description="Last month, YYYY-MM")

    @model_validator(mode="after")
    def start_before_end(self) -> Period:
        if self.start > self.end:
            raise ValueError(f"start ({self.start}) is after end ({self.end})")
        return self


class SeriesPoint(_Strict):
    date: str = Field(pattern=r"^\d{4}-\d{2}$", description="Month, YYYY-MM")
    value: float | None = Field(description="Value for the month; null if missing")


class Trend(_Strict):
    slope: float
    p: float = Field(ge=0, le=1, description="p-value from the trend test")
    tau: float = Field(ge=-1, le=1, description="Kendall's tau")
    trend: TrendDirection


class Results(_Strict):
    region: str = Field(min_length=1)
    variable: str = Field(min_length=1, description="e.g. Surface air temperature")
    units: str = Field(min_length=1, description="e.g. °C")
    period: Period
    series: list[SeriesPoint] = Field(min_length=1)
    trend: Trend
    explanation: str | None = None

class MapPoint(_Strict):
    """ESD-D13. The trend of one grid cell, at the cell's center.

    slope, p, tau and trend are all null when the cell has too few months with
    values to test (the same 24-month rule as the area trend).
    """

    lat: float = Field(ge=-90, le=90, description="Cell center latitude, degrees north")
    lon: float = Field(ge=-180, le=180, description="Cell center longitude, degrees east")
    slope: float | None = Field(description="Change per month, in `units`")
    p: float | None = Field(default=None, ge=0, le=1)
    tau: float | None = Field(default=None, ge=-1, le=1)
    trend: TrendDirection | None = None

    @model_validator(mode="after")
    def all_or_nothing(self) -> MapPoint:
        tested = [self.slope is not None, self.p is not None,
                  self.tau is not None, self.trend is not None]
        if any(tested) and not all(tested):
            raise ValueError("slope, p, tau and trend must all be set, or all be null")
        return self


class MapResults(_Strict):
    """ESD-D13. The per-cell trend map file (results/trend_map.json)."""

    region: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    units: str = Field(min_length=1)
    period: Period
    test: str = Field(min_length=1, description="Name of the trend test used per cell")
    resolution_deg: float = Field(gt=0, le=10, description="Grid spacing in degrees")
    points: list[MapPoint] = Field(min_length=1)

class ContractError(ValueError):
    """A results file is missing, is not JSON, or does not match the contract."""


def _format_errors(error: ValidationError) -> str:
    lines = []
    for err in error.errors():
        location = ".".join(str(part) for part in err["loc"]) or "(top level)"
        lines.append(f"  - {location}: {err['msg']}")
    return "\n".join(lines)


def load_results(path: str | Path) -> Results:
    """Read and validate a results JSON file, raising ContractError with a readable message."""
    return _load(path, Results, "results contract")


def load_map(path: str | Path) -> MapResults:
    """ESD-D13. Read and validate a trend map JSON file, raising ContractError if bad."""
    return _load(path, MapResults, "map contract")


def _load(path: str | Path, model, name: str):
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ContractError(f"{path}: file not found") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(
            f"{path}: not valid JSON (line {exc.lineno}, column {exc.colno}: {exc.msg})"
        ) from exc

    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ContractError(
            f"{path} does not match the {name}:\n{_format_errors(exc)}"
        ) from exc