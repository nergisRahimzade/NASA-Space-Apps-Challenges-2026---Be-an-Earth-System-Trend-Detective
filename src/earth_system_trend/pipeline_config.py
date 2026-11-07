"""Load and validate config.yaml for the config-driven pipeline (ESD-D15-BE)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    bbox: list[float] = Field(min_length=4, max_length=4)

    @field_validator("bbox")
    @classmethod
    def check_bbox(cls, v: list[float]) -> list[float]:
        lon_min, lat_min, lon_max, lat_max = v
        if not (-180 <= lon_min < lon_max <= 360):
            raise ValueError("bbox longitudes must satisfy lon_min < lon_max")
        if not (-90 <= lat_min < lat_max <= 90):
            raise ValueError("bbox latitudes must satisfy lat_min < lat_max within [-90, 90]")
        return v


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: str  # "YYYY-MM"
    end: str

    @model_validator(mode="after")
    def check_order(self) -> Period:
        import pandas as pd

        try:
            s, e = pd.Period(self.start, "M"), pd.Period(self.end, "M")
        except Exception as exc:
            raise ValueError(f"period dates must look like YYYY-MM: {exc}") from exc
        if s > e:
            raise ValueError("period.start must be before period.end")
        return self


class TrendSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    test: Literal["original", "seasonal", "hamed_rao"] = "seasonal"
    alpha: float = Field(0.05, gt=0, lt=1)
    min_points: int = Field(24, ge=4)


class SeriesSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time_column: str = "time"
    value_column: str = "value"


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region: Region
    period: Period
    trend: TrendSettings = TrendSettings()
    series: SeriesSettings = SeriesSettings()


class Hooks(BaseModel):
    model_config = ConfigDict(extra="forbid")
    download: str | None = None
    clean: str | None = None
    series: str | None = None
    explain: str | None = None

    @field_validator("*")
    @classmethod
    def check_hook(cls, v: str | None) -> str | None:
        if v is not None and ":" not in v:
            raise ValueError(f"hook '{v}' must look like 'package.module:function'")
        return v


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results_dir: str = "results"
    primary_variable: str | None = None


class VariableConfig(BaseModel):
    """One variable. Any field left out falls back to `defaults`."""

    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[A-Za-z0-9_\-]+$")
    long_name: str | None = None
    units: str
    series_path: str
    enabled: bool = True
    region: Region | None = None
    period: Period | None = None
    trend: TrendSettings | None = None
    series: SeriesSettings | None = None


class ResolvedVariable(BaseModel):
    """A variable with defaults merged in - what each pipeline run actually uses."""

    name: str
    long_name: str
    units: str
    series_path: Path
    region: Region
    period: Period
    trend: TrendSettings
    series: SeriesSettings

    def fingerprint(self) -> str:
        """Hash of every setting that affects the result (used to decide skip vs re-run)."""
        payload = self.model_dump(mode="json")
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    contract_version: str = "1.2"
    defaults: Defaults
    hooks: Hooks = Hooks()
    output: Output = Output()
    variables: list[VariableConfig] = Field(min_length=1)
    base_dir: Path = Path(".")  # set by load_config; relative paths resolve against it

    @model_validator(mode="after")
    def check_variables(self) -> PipelineConfig:
        names = [v.name for v in self.variables]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"duplicate variable names: {sorted(dupes)}")
        primary = self.output.primary_variable
        if primary is not None and primary not in names:
            raise ValueError(f"output.primary_variable '{primary}' is not in variables")
        return self

    def resolve(self, only: list[str] | None = None) -> list[ResolvedVariable]:
        """Return enabled variables (or exactly `only`) with defaults applied."""
        names = {v.name for v in self.variables}
        if only:
            unknown = sorted(set(only) - names)
            if unknown:
                raise ValueError(f"unknown variable(s): {unknown}. Known: {sorted(names)}")
        chosen = [v for v in self.variables if (v.name in only if only else v.enabled)]
        d = self.defaults
        return [
            ResolvedVariable(
                name=v.name,
                long_name=v.long_name or v.name,
                units=v.units,
                series_path=self.resolve_path(v.series_path),
                region=v.region or d.region,
                period=v.period or d.period,
                trend=v.trend or d.trend,
                series=v.series or d.series,
            )
            for v in chosen
        ]

    def resolve_path(self, p: str | Path) -> Path:
        p = Path(p)
        return p if p.is_absolute() else (self.base_dir / p)

    @property
    def results_dir(self) -> Path:
        return self.resolve_path(self.output.results_dir)


def load_config(path: str | Path = "config.yaml") -> PipelineConfig:
    """Read YAML and validate. Raises FileNotFoundError or pydantic.ValidationError."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path.resolve()}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise TypeError(f"{path} must contain a YAML mapping at the top level")
    raw["base_dir"] = path.resolve().parent
    return PipelineConfig.model_validate(raw)