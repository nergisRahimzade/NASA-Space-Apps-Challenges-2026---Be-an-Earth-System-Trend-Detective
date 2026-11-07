"""Tests for ESD-D15-BE: config-driven pipeline (read config.yaml, loop variables, contract v1.2).

Run:  uv run --locked pytest tests/test_pipeline_day15.py -v
Everything runs in a temporary folder with synthetic data: no NASA files, no API key.
"""

from __future__ import annotations

import json
import os
import sys
import time
import types

import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from earth_system_trend.pipeline import (
    FALLBACK_EXPLANATION,
    compute_trend,
    load_series,
    main,
    run_pipeline,
)
from earth_system_trend.pipeline_config import load_config
from earth_system_trend.pipeline_contract import ResultsIndex, ResultsV12

START, END = "2003-01", "2022-12"  # 20 years, 240 months


# --------------------------------------------------------------------------- helpers
def make_series(slope_per_year: float, noise: float = 0.2, seed: int = 0,
                start: str = START, end: str = END) -> pd.DataFrame:
    months = pd.period_range(start, end, freq="M")
    t = np.arange(len(months)) / 12.0
    rng = np.random.default_rng(seed)
    values = 15 + 5 * np.sin(2 * np.pi * t) + slope_per_year * t + rng.normal(0, noise, len(t))
    return pd.DataFrame({"time": months.to_timestamp().strftime("%Y-%m-%d"), "value": values})


def base_config(**overrides) -> dict:
    cfg = {
        "contract_version": "1.2",
        "defaults": {
            "region": {"name": "Test box", "bbox": [-10.0, 40.0, 0.0, 50.0]},
            "period": {"start": START, "end": END},
            "trend": {"test": "seasonal", "alpha": 0.05, "min_points": 24},
            "series": {"time_column": "time", "value_column": "value"},
        },
        "hooks": {},
        "output": {"results_dir": "results", "primary_variable": "warm"},
        "variables": [
            {"name": "warm", "long_name": "Warming var", "units": "degC",
             "series_path": "data/processed/timeseries_warm.csv"},
            {"name": "flat", "long_name": "Flat var", "units": "mm",
             "series_path": "data/processed/timeseries_flat.csv"},
            {"name": "off", "long_name": "Disabled var", "units": "K",
             "series_path": "data/processed/timeseries_off.csv", "enabled": False},
        ],
    }
    cfg.update(overrides)
    return cfg


@pytest.fixture
def project(tmp_path):
    """A throwaway project folder with config.yaml and three series CSVs."""
    data = tmp_path / "data" / "processed"
    data.mkdir(parents=True)
    make_series(0.05, seed=1).to_csv(data / "timeseries_warm.csv", index=False)
    make_series(0.0, noise=0.0).to_csv(data / "timeseries_flat.csv", index=False)
    make_series(-0.05, seed=3).to_csv(data / "timeseries_off.csv", index=False)
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(base_config(), sort_keys=False))
    return tmp_path


def write_cfg(project, cfg: dict):
    (project / "config.yaml").write_text(yaml.safe_dump(cfg, sort_keys=False))
    return load_config(project / "config.yaml")


def read_result(project, name: str) -> ResultsV12:
    return ResultsV12.model_validate_json(
        (project / "results" / name / "results.json").read_text())


# --------------------------------------------------------------------------- 1. read config.yaml
def test_config_loads_and_merges_defaults(project):
    cfg = load_config(project / "config.yaml")
    resolved = cfg.resolve()
    assert [v.name for v in resolved] == ["warm", "flat"]  # disabled one left out
    warm = resolved[0]
    assert warm.region.name == "Test box"
    assert warm.trend.test == "seasonal"
    assert warm.series_path == project / "data/processed/timeseries_warm.csv"


def test_per_variable_override_beats_defaults(project):
    raw = base_config()
    raw["variables"][1]["trend"] = {"test": "original", "alpha": 0.01, "min_points": 24}
    raw["variables"][1]["region"] = {"name": "Other box", "bbox": [0, 0, 10, 10]}
    flat = write_cfg(project, raw).resolve(["flat"])[0]
    assert flat.trend.test == "original" and flat.trend.alpha == 0.01
    assert flat.region.name == "Other box"


@pytest.mark.parametrize("mutate, message", [
    (lambda c: c["variables"].append(dict(c["variables"][0])), "duplicate"),
    (lambda c: c["hooks"].update(download="no_colon_here"), "package.module:function"),
    (lambda c: c["defaults"]["region"].update(bbox=[10, 0, 0, 10]), "lon_min < lon_max"),
    (lambda c: c["output"].update(primary_variable="nope"), "primary_variable"),
    (lambda c: c["defaults"]["period"].update(start="2030-01"), "before period.end"),
    (lambda c: c["defaults"]["trend"].update(test="magic"), "test"),
    (lambda c: c.update(variables=[]), "variables"),
    (lambda c: c.update(surprise_key=1), "surprise_key"),
])
def test_bad_config_is_rejected_with_clear_error(project, mutate, message):
    raw = base_config()
    mutate(raw)
    with pytest.raises(ValidationError, match=message):
        write_cfg(project, raw)


def test_missing_config_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


# --------------------------------------------------------------------------- 2. loop variables
def test_one_command_runs_every_enabled_variable(project):
    outcomes = run_pipeline(load_config(project / "config.yaml"))
    assert {o.name: o.status for o in outcomes} == {"warm": "ok", "flat": "ok"}
    assert (project / "results/warm/results.json").exists()
    assert (project / "results/flat/results.json").exists()
    assert not (project / "results/off/results.json").exists()


def test_trend_results_are_correct_per_variable(project):
    run_pipeline(load_config(project / "config.yaml"))
    warm, flat = read_result(project, "warm"), read_result(project, "flat")

    assert warm.trend.trend == "increasing" and warm.trend.significant
    assert warm.trend.slope_per_year == pytest.approx(0.05, rel=0.25)
    assert warm.trend.slope_unit == "degC per year"
    assert warm.variable.units == "degC"

    assert flat.trend.trend == "no trend" and not flat.trend.significant
    assert flat.variable.units == "mm"
    assert len(warm.series) == 240 and warm.series[0].time == "2003-01"


def test_named_variable_runs_even_if_disabled(project):
    outcomes = run_pipeline(load_config(project / "config.yaml"), only=["off"])
    assert [o.name for o in outcomes] == ["off"]
    assert read_result(project, "off").trend.trend == "decreasing"


def test_unknown_variable_is_an_error(project):
    with pytest.raises(ValueError, match="unknown variable"):
        run_pipeline(load_config(project / "config.yaml"), only=["ghost"])


def test_adding_a_variable_needs_only_config(project):
    make_series(0.1, seed=9).to_csv(project / "data/processed/new.csv", index=False)
    raw = base_config()
    raw["variables"].append({"name": "brand_new", "units": "W m-2",
                             "series_path": "data/processed/new.csv"})
    outcomes = run_pipeline(write_cfg(project, raw))
    assert "brand_new" in {o.name for o in outcomes if o.status == "ok"}
    assert read_result(project, "brand_new").variable.long_name == "brand_new"


def test_one_failing_variable_does_not_stop_the_others(project):
    (project / "data/processed/timeseries_flat.csv").unlink()
    outcomes = {o.name: o for o in run_pipeline(load_config(project / "config.yaml"))}
    assert outcomes["warm"].status == "ok"
    assert outcomes["flat"].status == "failed" and "not found" in outcomes["flat"].error


# --------------------------------------------------------------------------- 3. skip / re-run
def test_second_run_skips_and_force_rebuilds(project):
    cfg = load_config(project / "config.yaml")
    run_pipeline(cfg)
    assert {o.status for o in run_pipeline(cfg)} == {"skipped"}
    assert {o.status for o in run_pipeline(cfg, force=True)} == {"ok"}


def test_changed_settings_trigger_rerun(project):
    run_pipeline(load_config(project / "config.yaml"))
    raw = base_config()
    raw["variables"][0]["units"] = "K"
    outcomes = {o.name: o.status for o in run_pipeline(write_cfg(project, raw))}
    assert outcomes == {"warm": "ok", "flat": "skipped"}


def test_newer_series_file_triggers_rerun(project):
    cfg = load_config(project / "config.yaml")
    run_pipeline(cfg)
    series = project / "data/processed/timeseries_flat.csv"
    future = time.time() + 5
    os.utime(series, (future, future))
    assert {o.name: o.status for o in run_pipeline(cfg)} == {"warm": "skipped", "flat": "ok"}


# --------------------------------------------------------------------------- 4. contract v1.2
def test_outputs_match_contract_and_keep_v11_fields(project):
    run_pipeline(load_config(project / "config.yaml"))
    raw = json.loads((project / "results/warm/results.json").read_text())
    for v11_field in ("region", "period", "series", "trend", "explanation"):
        assert v11_field in raw
    for k in ("slope", "p", "tau", "trend"):
        assert k in raw["trend"]
    assert raw["contract_version"] == "1.2"
    ResultsV12.model_validate(raw)


def test_index_and_legacy_results_file(project):
    run_pipeline(load_config(project / "config.yaml"))
    index = ResultsIndex.model_validate_json((project / "results/index.json").read_text())
    assert index.primary_variable == "warm"
    assert {e.variable for e in index.variables} == {"warm", "flat"}
    assert all((project / "results" / e.path).exists() for e in index.variables)
    legacy = ResultsV12.model_validate_json((project / "results/results.json").read_text())
    assert legacy.variable.name == "warm"


def test_json_has_no_nan(project):
    df = make_series(0.05, seed=1)
    df.loc[10:15, "value"] = np.nan
    df.to_csv(project / "data/processed/timeseries_warm.csv", index=False)
    run_pipeline(load_config(project / "config.yaml"))
    text = (project / "results/warm/results.json").read_text()
    assert "NaN" not in text
    warm = read_result(project, "warm")
    assert sum(p.value is None for p in warm.series) == 6
    assert warm.trend.n == 234


# --------------------------------------------------------------------------- 5. series edge cases
def test_insufficient_data_is_reported_not_crashed(project):
    make_series(0.05, start="2022-01", end="2022-12").to_csv(
        project / "data/processed/timeseries_warm.csv", index=False)
    run_pipeline(load_config(project / "config.yaml"), only=["warm"])
    t = read_result(project, "warm").trend
    assert t.trend == "insufficient data" and t.p is None and t.n == 12 and not t.significant


def test_custom_column_names_and_daily_rows(project):
    days = pd.date_range("2003-01-01", "2022-12-31", freq="D")
    df = pd.DataFrame({"date": days, "lst_c": 20 + 0.0001 * np.arange(len(days)), "qc": 1})
    df.to_csv(project / "data/processed/timeseries_warm.csv", index=False)
    raw = base_config()
    raw["variables"][0]["series"] = {"time_column": "date", "value_column": "lst_c"}
    var = write_cfg(project, raw).resolve(["warm"])[0]
    s = load_series(var)
    assert len(s) == 240 and s.notna().all()  # daily rows averaged to months


def test_wrong_columns_give_helpful_error(project):
    pd.DataFrame({"a": [1], "b": [2], "c": [3]}).to_csv(
        project / "data/processed/timeseries_warm.csv", index=False)
    var = load_config(project / "config.yaml").resolve(["warm"])[0]
    with pytest.raises(ValueError, match="series.time_column"):
        load_series(var)


@pytest.mark.parametrize("test_name, unit", [
    ("original", "degC per month"), ("hamed_rao", "degC per month"), ("seasonal", "degC per year"),
])
def test_every_configured_test_runs(project, test_name, unit):
    raw = base_config()
    raw["defaults"]["trend"]["test"] = test_name
    var = write_cfg(project, raw).resolve(["warm"])[0]
    t = compute_trend(load_series(var), var)
    assert t["test"] == test_name and t["slope_unit"] == unit
    assert t["slope_per_year"] > 0


# --------------------------------------------------------------------------- 6. hooks
@pytest.fixture
def fake_hooks(monkeypatch):
    mod = types.ModuleType("fake_hooks")
    mod.calls = []

    def build_series(var):
        mod.calls.append(("series", var.name))
        var.series_path.parent.mkdir(parents=True, exist_ok=True)
        make_series(0.05, seed=5).to_csv(var.series_path, index=False)

    def explain(payload):
        mod.calls.append(("explain", payload["variable"]["name"]))
        assert "explanation" not in payload
        return f"{payload['variable']['long_name']} is {payload['trend']['trend']}."

    def explain_boom(payload):
        raise TimeoutError("AI timed out")

    mod.build_series, mod.explain, mod.explain_boom = build_series, explain, explain_boom
    monkeypatch.setitem(sys.modules, "fake_hooks", mod)
    return mod


def test_series_hook_builds_missing_file_and_is_skipped_when_present(project, fake_hooks):
    (project / "data/processed/timeseries_warm.csv").unlink()
    raw = base_config(hooks={"series": "fake_hooks:build_series"})
    cfg = write_cfg(project, raw)
    run_pipeline(cfg)
    assert fake_hooks.calls == [("series", "warm")]  # flat's file exists, so not rebuilt
    assert read_result(project, "warm").trend.trend == "increasing"


def test_explain_hook_text_is_stored(project, fake_hooks):
    run_pipeline(write_cfg(project, base_config(hooks={"explain": "fake_hooks:explain"})))
    assert read_result(project, "warm").explanation == "Warming var is increasing."
    assert read_result(project, "flat").explanation == "Flat var is no trend."


def test_failing_explain_falls_back(project, fake_hooks):
    cfg = write_cfg(project, base_config(hooks={"explain": "fake_hooks:explain_boom"}))
    outcomes = run_pipeline(cfg)
    assert {o.status for o in outcomes} == {"ok"}
    assert read_result(project, "warm").explanation == FALLBACK_EXPLANATION


def test_unloadable_hook_fails_loudly(project):
    cfg = write_cfg(project, base_config(hooks={"download": "not_a_module:x"}))
    with pytest.raises(RuntimeError, match="cannot load hook"):
        run_pipeline(cfg)


# --------------------------------------------------------------------------- 7. CLI
def test_cli_exit_codes(project, capsys):
    cfg = str(project / "config.yaml")
    assert main(["--config", cfg]) == 0
    assert "warm" in capsys.readouterr().out
    assert main(["--config", cfg, "--variable", "ghost"]) == 2
    assert main(["--config", str(project / "missing.yaml")]) == 2
    (project / "data/processed/timeseries_flat.csv").unlink()
    assert main(["--config", cfg, "--force"]) == 1
    assert main(["--config", cfg, "--list"]) == 0