"""Config-driven pipeline (ESD-D15-BE): one command, any variable.

    uv run --locked python -m earth_system_trend.pipeline                 # all enabled variables
    uv run --locked python -m earth_system_trend.pipeline --variable sst  # just one
    uv run --locked python -m earth_system_trend.pipeline --force         # ignore existing outputs

For each variable: [download hook] -> [clean hook] -> [series hook] -> load series ->
trend -> [explain hook] -> results/<variable>/results.json. Then results/index.json, and the
primary variable is also copied to results/results.json so the existing API keeps working.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import math
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from earth_system_trend.pipeline_config import (
    PipelineConfig,
    ResolvedVariable,
    load_config,
)
from earth_system_trend.pipeline_contract import IndexEntry, ResultsIndex, ResultsV12

log = logging.getLogger("earth_system_trend.pipeline")

FALLBACK_EXPLANATION = (
    "An AI explanation is not available for this result. "
    "See the trend statistics shown alongside the chart."
)


# --------------------------------------------------------------------------- hooks
def import_hook(spec: str | None) -> Callable[..., Any] | None:
    """Turn 'package.module:function' into a callable. None means 'no hook'."""
    if not spec:
        return None
    module_name, _, func_name = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(f"cannot load hook '{spec}': {exc}") from exc
    if not callable(func):
        raise TypeError(f"hook '{spec}' is not callable")
    return func


# --------------------------------------------------------------------------- series
def load_series(var: ResolvedVariable) -> pd.Series:
    """Read the variable's CSV and return a monthly series covering exactly var.period.

    Missing months become NaN; several rows in one month are averaged.
    """
    path = var.series_path
    if not path.exists():
        raise FileNotFoundError(
            f"series file for '{var.name}' not found: {path}. "
            "Create it with the data layer, or set hooks.series in config.yaml."
        )
    df = pd.read_csv(path)
    tcol, vcol = var.series.time_column, var.series.value_column
    if tcol not in df.columns or vcol not in df.columns:
        if len(df.columns) == 2:
            tcol, vcol = df.columns[0], df.columns[1]
            log.warning("[%s] columns %s not found; using %s/%s",
                        var.name, (var.series.time_column, var.series.value_column), tcol, vcol)
        else:
            raise ValueError(
                f"{path} needs columns '{var.series.time_column}' and "
                f"'{var.series.value_column}' (found {list(df.columns)}); "
                "set series.time_column / series.value_column in config.yaml"
            )
    times = pd.to_datetime(df[tcol], errors="coerce")
    if times.isna().all():
        raise ValueError(f"{path}: column '{tcol}' has no parseable dates")
    values = pd.to_numeric(df[vcol], errors="coerce")
    s = pd.Series(values.to_numpy(), index=times.dt.to_period("M")).dropna()
    s = s[~s.index.isna()].groupby(level=0).mean().sort_index()

    full = pd.period_range(var.period.start, var.period.end, freq="M")
    return s.reindex(full)


# --------------------------------------------------------------------------- trend
def _clean(x: Any, nd: int = 6) -> float | None:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else round(f, nd)


def compute_trend(series: pd.Series, var: ResolvedVariable) -> dict[str, Any]:
    """Mann-Kendall test chosen in config. Returns contract v1.2 `trend` fields."""
    settings = var.trend
    valid = series.dropna()
    n = int(valid.size)
    per_year_factor = 1.0 if settings.test == "seasonal" else 12.0  # seasonal slope is per year
    slope_unit = f"{var.units} per {'year' if settings.test == 'seasonal' else 'month'}"
    base = {"test": settings.test, "slope_unit": slope_unit, "n": n}

    if n < settings.min_points:
        log.warning("[%s] only %d valid months (< %d): insufficient data",
                    var.name, n, settings.min_points)
        return {**base, "slope": None, "p": None, "tau": None,
                "trend": "insufficient data", "significant": False, "slope_per_year": None}

    import pymannkendall as mk

    values = series.to_numpy(dtype=float)  # keep NaN gaps so seasons stay aligned
    if settings.test == "seasonal":
        r = mk.seasonal_test(values, period=12, alpha=settings.alpha)
    elif settings.test == "hamed_rao":
        r = mk.hamed_rao_modification_test(valid.to_numpy(dtype=float), alpha=settings.alpha)
    else:
        r = mk.original_test(valid.to_numpy(dtype=float), alpha=settings.alpha)

    p = _clean(r.p, 8)
    slope = _clean(r.slope, 8)
    label = r.trend if r.trend in ("increasing", "decreasing") else "no trend"
    significant = bool(p is not None and p < settings.alpha and label != "no trend")
    return {
        **base,
        "slope": slope,
        "p": p,
        "tau": _clean(r.Tau, 6),
        "trend": label,
        "significant": significant,
        "slope_per_year": None if slope is None else round(slope * per_year_factor, 8),
    }


# --------------------------------------------------------------------------- per variable
@dataclass
class VariableOutcome:
    name: str
    status: str  # "ok" | "skipped" | "failed"
    path: Path | None = None
    error: str | None = None
    steps: list[str] = field(default_factory=list)


def results_path(config: PipelineConfig, name: str) -> Path:
    return config.results_dir / name / "results.json"


def _is_fresh(out: Path, var: ResolvedVariable) -> bool:
    """Existing output is reusable if made with identical settings from an unchanged series."""
    if not out.exists():
        return False
    try:
        meta = json.loads(out.read_text(encoding="utf-8")).get("meta", {})
    except (OSError, json.JSONDecodeError):
        return False
    if meta.get("config_fingerprint") != var.fingerprint():
        return False
    series_newer = (var.series_path.exists()
                    and var.series_path.stat().st_mtime > out.stat().st_mtime)
    return not series_newer


def run_variable(config: PipelineConfig, var: ResolvedVariable, force: bool = False,
                 hooks: dict[str, Callable[..., Any] | None] | None = None) -> VariableOutcome:
    out = results_path(config, var.name)
    outcome = VariableOutcome(name=var.name, status="ok", path=out)
    hooks = hooks or {}

    if not force and _is_fresh(out, var):
        log.info("[%s] up to date -> skip (use --force to rebuild)", var.name)
        outcome.status = "skipped"
        return outcome

    # Steps that produce the series file: skipped when the file already exists.
    for step in ("download", "clean", "series"):
        hook = hooks.get(step)
        if hook is None:
            log.info("[%s] %s: no hook configured -> skip", var.name, step)
            continue
        if var.series_path.exists() and not force:
            log.info("[%s] %s: series file exists -> skip", var.name, step)
            continue
        log.info("[%s] %s: running %s", var.name, step, getattr(hook, "__name__", hook))
        hook(var)
        outcome.steps.append(step)

    series = load_series(var)
    log.info("[%s] series: %d months, %d valid", var.name, series.size, int(series.notna().sum()))
    outcome.steps.append("series_loaded")

    trend = compute_trend(series, var)
    log.info("[%s] trend: %s (p=%s, slope=%s %s)", var.name, trend["trend"],
             trend["p"], trend["slope"], trend["slope_unit"])
    outcome.steps.append("trend")

    payload: dict[str, Any] = {
        "contract_version": "1.2",
        "variable": {"name": var.name, "long_name": var.long_name, "units": var.units},
        "region": var.region.model_dump(),
        "period": var.period.model_dump(),
        "series": [{"time": str(t), "value": _clean(v)} for t, v in series.items()],
        "trend": trend,
    }

    explanation = FALLBACK_EXPLANATION
    explain = hooks.get("explain")
    if explain is not None:
        try:
            text = explain(payload)
            if isinstance(text, str) and text.strip():
                explanation = text.strip()
                outcome.steps.append("explain")
            else:
                log.warning("[%s] explain hook returned empty text -> fallback", var.name)
        except Exception as exc:  # noqa: BLE001 - AI failure must never break the pipeline
            log.warning("[%s] explain hook failed (%s) -> fallback", var.name, exc)
    payload["explanation"] = explanation
    payload["meta"] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "config_fingerprint": var.fingerprint(),
        "source_file": str(var.series_path),
    }

    validated = ResultsV12.model_validate(payload)  # never write a file that breaks the contract
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(validated.model_dump_json(indent=2), encoding="utf-8")
    log.info("[%s] wrote %s", var.name, out)
    outcome.steps.append("written")
    return outcome


# --------------------------------------------------------------------------- whole run
def write_index(config: PipelineConfig) -> Path:
    """results/index.json lists every variable that has a valid results file."""
    entries = []
    for v in config.variables:
        p = results_path(config, v.name)
        if not p.exists():
            continue
        r = ResultsV12.model_validate_json(p.read_text(encoding="utf-8"))
        entries.append(IndexEntry(
            variable=r.variable.name, long_name=r.variable.long_name, units=r.variable.units,
            path=p.relative_to(config.results_dir).as_posix(),
            trend=r.trend.trend, significant=r.trend.significant,
        ))
    index = ResultsIndex(
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        primary_variable=config.output.primary_variable,
        variables=entries,
    )
    out = config.results_dir / "index.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(index.model_dump_json(indent=2), encoding="utf-8")
    return out


def run_pipeline(config: PipelineConfig, only: list[str] | None = None,
                 force: bool = False) -> list[VariableOutcome]:
    variables = config.resolve(only)
    if not variables:
        log.warning("no enabled variables in config; nothing to do")
    hooks = {name: import_hook(getattr(config.hooks, name))
             for name in ("download", "clean", "series", "explain")}

    outcomes = []
    for var in variables:
        try:
            outcomes.append(run_variable(config, var, force=force, hooks=hooks))
        except Exception as exc:  # noqa: BLE001 - one bad variable must not stop the rest
            log.error("[%s] FAILED: %s", var.name, exc)
            outcomes.append(VariableOutcome(name=var.name, status="failed", error=str(exc)))

    write_index(config)
    primary = config.output.primary_variable
    if primary and results_path(config, primary).exists():
        legacy = config.results_dir / "results.json"
        legacy.write_text(results_path(config, primary).read_text(encoding="utf-8"),
                          encoding="utf-8")
        log.info("primary variable '%s' copied to %s", primary, legacy)
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the config-driven trend pipeline.")
    parser.add_argument("--config", default="config.yaml", help="path to config.yaml")
    parser.add_argument("--variable", action="append", dest="variables",
                        help="run only this variable (repeatable); runs it even if disabled")
    parser.add_argument("--force", action="store_true", help="rebuild even if outputs exist")
    parser.add_argument("--list", action="store_true", help="list variables and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    try:
        config = load_config(args.config)
    except Exception as exc:  # noqa: BLE001
        log.error("invalid config: %s", exc)
        return 2

    if args.list:
        for v in config.variables:
            print(f"{v.name:<12} {'enabled ' if v.enabled else 'disabled'}  {v.units:<8} "
                  f"{v.series_path}")
        return 0

    try:
        outcomes = run_pipeline(config, only=args.variables, force=args.force)
    except ValueError as exc:  # e.g. unknown --variable
        log.error("%s", exc)
        return 2

    print("\nSummary")
    for o in outcomes:
        detail = o.error if o.status == "failed" else (o.path or "")
        print(f"  {o.name:<12} {o.status:<8} {detail}")
    return 1 if any(o.status == "failed" for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())