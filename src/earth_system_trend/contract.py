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

# --- API answers (ESD-D14-BE) ---------------------------------------------------
# The exact shape of each endpoint's JSON answer. The end-to-end test checks
# real API answers against these, so a renamed or extra field fails loudly.


class Health(_Strict):
    status: Literal["ok"]


class RegionSummary(_Strict):
    """One entry of GET /regions: a region without its monthly series."""

    id: str = Field(pattern=r"^[a-z0-9_]+$", description="Short name used in ?region=")
    region: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    units: str = Field(min_length=1)
    period: Period
    trend: Trend


class RegionsResponse(_Strict):
    regions: list[RegionSummary] = Field(min_length=1)


class SeriesResponse(_Strict):
    """GET /series?region=..."""

    region: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    units: str = Field(min_length=1)
    period: Period
    series: list[SeriesPoint] = Field(min_length=1)


class TrendResponse(_Strict):
    """GET /trend and GET /trend?region=..."""

    region: str = Field(min_length=1)
    variable: str = Field(min_length=1)
    units: str = Field(min_length=1)
    period: Period
    trend: Trend
    explanation: str | None

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
        return Results.model_validate(data)
    except ValidationError as exc:
        raise ContractError(
            f"{path} does not match the results contract:\n{_format_errors(exc)}"
        ) from exc