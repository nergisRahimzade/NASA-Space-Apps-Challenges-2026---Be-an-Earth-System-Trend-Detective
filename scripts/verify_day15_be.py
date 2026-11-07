"""Acceptance check for ESD-D15-BE: "One command, any variable".

Run from the repository root:
    uv run --locked python scripts/verify_day15_be.py

Uses a temporary folder with synthetic data, so it needs no NASA files and no API key.
Exits 0 only if every check passes.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    return ok


def fake_csv(path: Path, slope: float, seed: int) -> None:
    months = pd.period_range("2003-01", "2022-12", freq="M")
    t = np.arange(len(months)) / 12.0
    noise = np.random.default_rng(seed).normal(0, 0.2, len(t))
    v = 10 + 4 * np.sin(2 * np.pi * t) + slope * t + noise
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"time": months.to_timestamp(), "value": v}).to_csv(path, index=False)


def run_cli(cfg: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "earth_system_trend.pipeline", "--config", str(cfg), *extra],
        capture_output=True, text=True, cwd=ROOT, check=False,
    )


def statuses(proc: subprocess.CompletedProcess) -> dict[str, str]:
    out, in_summary = {}, False
    for line in proc.stdout.splitlines():
        if line.strip() == "Summary":
            in_summary = True
            continue
        parts = line.split()
        if in_summary and len(parts) >= 2:
            out[parts[0]] = parts[1]
    return out


def main() -> int:
    print("ESD-D15-BE verification\n\n1. Files in place")
    for rel in ("config.yaml", "src/earth_system_trend/pipeline_config.py",
                "src/earth_system_trend/pipeline_contract.py",
                "src/earth_system_trend/pipeline.py", "tests/test_pipeline_day15.py"):
        check(rel, (ROOT / rel).exists(), "missing")

    print("\n2. Imports and repo config.yaml")
    try:
        from earth_system_trend.pipeline_config import load_config
        from earth_system_trend.pipeline_contract import ResultsIndex, ResultsV12
        check("modules import", True)
    except Exception as exc:  # noqa: BLE001
        check("modules import", False, f"{exc}; run `uv sync --locked`")
        return summarize()
    try:
        cfg = load_config(ROOT / "config.yaml")
        check("repo config.yaml is valid", True)
        check("repo config.yaml lists >= 1 enabled variable", len(cfg.resolve()) >= 1)
    except Exception as exc:  # noqa: BLE001
        check("repo config.yaml is valid", False, str(exc).splitlines()[0])

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fake_csv(tmp / "data/a.csv", 0.05, 1)
        fake_csv(tmp / "data/b.csv", -0.05, 2)
        config = {
            "defaults": {"region": {"name": "Box", "bbox": [-10, 40, 0, 50]},
                         "period": {"start": "2003-01", "end": "2022-12"}},
            "output": {"results_dir": "results", "primary_variable": "var_a"},
            "variables": [
                {"name": "var_a", "units": "degC", "series_path": "data/a.csv"},
                {"name": "var_b", "units": "mm", "series_path": "data/b.csv"},
            ],
        }
        cfg_path = tmp / "config.yaml"
        cfg_path.write_text(yaml.safe_dump(config))

        print("\n3. One command runs every variable")
        p = run_cli(cfg_path)
        check("CLI exits 0", p.returncode == 0, p.stderr[-400:])
        check("both variables ran", statuses(p) == {"var_a": "ok", "var_b": "ok"}, str(statuses(p)))
        for name, expected in (("var_a", "increasing"), ("var_b", "decreasing")):
            f = tmp / "results" / name / "results.json"
            try:
                r = ResultsV12.model_validate_json(f.read_text())
                check(f"{name}: valid contract v1.2", True)
                check(f"{name}: trend is {expected}", r.trend.trend == expected, r.trend.trend)
            except Exception as exc:  # noqa: BLE001
                check(f"{name}: valid contract v1.2", False, str(exc).splitlines()[0])
        try:
            idx = ResultsIndex.model_validate_json((tmp / "results/index.json").read_text())
            listed = {e.variable for e in idx.variables}
            check("index.json lists both", listed == {"var_a", "var_b"})
            legacy = json.loads((tmp / "results/results.json").read_text())
            check("results/results.json = primary variable", legacy["variable"]["name"] == "var_a")
        except Exception as exc:  # noqa: BLE001
            check("index.json / results.json written", False, str(exc).splitlines()[0])

        print("\n4. Skips finished work, --force rebuilds")
        p = run_cli(cfg_path)
        check("re-run skips both", set(statuses(p).values()) == {"skipped"}, str(statuses(p)))
        p = run_cli(cfg_path, "--force")
        check("--force rebuilds both", set(statuses(p).values()) == {"ok"}, str(statuses(p)))

        print("\n5. New variable = config change only")
        fake_csv(tmp / "data/c.csv", 0.1, 3)
        config["variables"].append({"name": "var_c", "units": "K", "series_path": "data/c.csv"})
        cfg_path.write_text(yaml.safe_dump(config))
        p = run_cli(cfg_path)
        expected = {"var_a": "skipped", "var_b": "skipped", "var_c": "ok"}
        check("only the new variable runs", statuses(p) == expected, str(statuses(p)))
        p = run_cli(cfg_path, "--variable", "var_b", "--force")
        check("--variable runs just one", list(statuses(p)) == ["var_b"], str(statuses(p)))

        print("\n6. Bad input handled")
        p = run_cli(cfg_path, "--variable", "ghost")
        check("unknown variable -> exit 2", p.returncode == 2)
        (tmp / "data/b.csv").unlink()
        p = run_cli(cfg_path, "--force")
        s = statuses(p)
        check("missing file fails one variable, others still ok",
              p.returncode == 1 and s.get("var_b") == "failed" and s.get("var_a") == "ok", str(s))

    print("\n7. Unit tests")
    t = subprocess.run([sys.executable, "-m", "pytest", "tests/test_pipeline_day15.py", "-q"],
                       capture_output=True, text=True, cwd=ROOT, check=False)
    last = (t.stdout.strip().splitlines() or ["no output"])[-1]
    check("pytest tests/test_pipeline_day15.py", t.returncode == 0, last)

    return summarize()


def summarize() -> int:
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    print("ESD-D15-BE DONE: one command, any variable" if not failed else f"NOT DONE: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())