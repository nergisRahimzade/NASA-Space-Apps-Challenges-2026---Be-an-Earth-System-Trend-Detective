"""results.json contract v1.2 (ESD-D15-BE).

v1.2 is additive over v1.1: every v1.1 field (region, period, series[], trend{slope,p,tau,trend},
explanation) keeps its name and meaning. New fields: contract_version, variable{}, trend.test,
trend.significant, trend.slope_unit, trend.slope_per_year, trend.n, meta{}.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TrendLabel = Literal["increasing", "decreasing", "no trend", "insufficient data"]


class VariableInfo(BaseModel):
    name: str
    long_name: str
    units: str


class RegionInfo(BaseModel):
    name: str
    bbox: list[float] = Field(min_length=4, max_length=4)


class PeriodInfo(BaseModel):
    start: str
    end: str


class SeriesPoint(BaseModel):
    time: str  # "YYYY-MM"
    value: float | None


class TrendInfo(BaseModel):
    slope: float | None
    p: float | None
    tau: float | None
    trend: TrendLabel
    # v1.2 additions
    test: str
    significant: bool
    slope_unit: str
    slope_per_year: float | None
    n: int


class Meta(BaseModel):
    generated_at: str
    config_fingerprint: str
    source_file: str


class ResultsV12(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: Literal["1.2"] = "1.2"
    variable: VariableInfo
    region: RegionInfo
    period: PeriodInfo
    series: list[SeriesPoint]
    trend: TrendInfo
    explanation: str
    meta: Meta


class IndexEntry(BaseModel):
    variable: str
    long_name: str
    units: str
    path: str  # relative to results dir
    trend: TrendLabel
    significant: bool


class ResultsIndex(BaseModel):
    contract_version: Literal["1.2"] = "1.2"
    generated_at: str
    primary_variable: str | None
    variables: list[IndexEntry]