"""End-to-end test: run the pipeline, serve its output through the API, check every answer.

ESD-D14-BE. Run from the project root:

    uv run --locked python -m earth_system_trend.e2e            # committed CSVs, API in-process
    uv run --locked python -m earth_system_trend.e2e --stub     # fake CSVs instead
    uv run --locked python -m earth_system_trend.e2e --live     # start a real uvicorn server

What it does:
  1. pipeline  build results.json and one file per sub-region in a temporary
               folder, from the Data layer's CSVs (or fake ones with --stub).
               Nothing in results/ is touched.
  2. API       point the API at those files (USE_MOCK=false) and ask it every
               endpoint: in-process by default, or over HTTP with --live.
  3. schema    check each answer against the contract models, and check that the
               API serves exactly what the pipeline wrote.

No OpenAI key is used unless you pass --with-ai, so CI never spends money; the
explanation step then uses its fallback text. Exits 0 if every check passes, else 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .config import DEFAULT_REGIONS_FILE, DEFAULT_SERIES_CSV, configure_logging
from .contract import (
    Health,
    RegionsResponse,
    Results,
    SeriesPoint,
    SeriesResponse,
    TrendResponse,
    load_results,
)
from .regions import slugify
from .run import (
    DEFAULT_REGION,
    DEFAULT_UNITS,
    DEFAULT_VARIABLE,
    PipelineError,
    load_region_list,
    run_all_regions,
    run_pipeline,
    write_stub_series,
)
from .timeseries import next_month

logger = logging.getLogger("earth_system_trend.e2e")

SIGNIFICANCE_LEVEL = 0.05  # pymannkendall's default alpha
UNKNOWN_REGION = "no_such_region_e2e"

# Fake sub-regions for --stub: (id, label, months), with different lengths so
# a mix-up between regions would show up as a mismatch.
STUB_REGIONS = [
    ("stub_north", "Stub north window", 264),
    ("stub_south", "Stub south window", 240),
    ("stub_east", "Stub east window", 216),
]


class E2EError(Exception):
    """Setup failed before any check could run (missing inputs, pipeline error, server down)."""


# --- 1. pipeline ------------------------------------------------------------------


@dataclass(frozen=True)
class Built:
    """Where the pipeline wrote its files, and what the API should therefore serve."""

    results_path: Path
    regions_dir: Path
    region_ids: list[str]  # sub-region ids from the regions file


def write_stub_inputs(folder: Path) -> tuple[Path, Path]:
    """Write a fake main CSV, fake sub-region CSVs and a regions file. Returns (csv, regions file)."""
    folder.mkdir(parents=True, exist_ok=True)
    main_csv = folder / "timeseries.csv"
    write_stub_series(main_csv)
    regions = {}
    for region_id, label, months in STUB_REGIONS:
        write_stub_series(folder / f"timeseries_{region_id}.csv", months=months)
        regions[region_id] = {"label": label}
    regions_file = folder / "subregions.json"
    regions_file.write_text(json.dumps({"regions": regions}, indent=2), encoding="utf-8")
    return main_csv, regions_file


def build(workdir: Path, main_csv: Path, regions_file: Path,
          region: str = DEFAULT_REGION, variable: str = DEFAULT_VARIABLE,
          units: str = DEFAULT_UNITS) -> Built:
    """Run the whole pipeline into workdir: the study area, then every sub-region."""
    if not main_csv.exists():
        raise E2EError(f"{main_csv} not found. Run the Data steps first, or use --stub.")
    results_path = workdir / "results" / "results.json"
    regions_dir = workdir / "results" / "regions"
    try:
        region_ids = list(load_region_list(regions_file))
        run_pipeline(main_csv, results_path, region, variable, units, force=True)
        # Sub-region CSVs sit next to the main CSV, as in the real pipeline.
        run_all_regions(regions_file, main_csv.parent, regions_dir, variable, units, force=True)
    except PipelineError as exc:
        raise E2EError(f"pipeline failed: {exc}") from exc
    return Built(results_path, regions_dir, region_ids)


# --- 2. API -----------------------------------------------------------------------

# A getter asks the API one GET and returns (status code, parsed JSON body).
Getter = Callable[[str, dict | None], tuple[int, Any]]


@contextmanager
def api_env(built: Built, cache_path: Path, with_ai: bool) -> Iterator[None]:
    """Point every setting at the e2e files for the duration of the test, then restore."""
    wanted = {
        "USE_MOCK": "false",
        "RESULTS_PATH": str(built.results_path),
        "REGIONS_DIR": str(built.regions_dir),
        "EXPLAIN_CACHE_PATH": str(cache_path),
        "RATE_LIMIT_PER_MINUTE": "0",  # the checks make many requests in a row
    }
    if not with_ai:
        wanted["OPENAI_API_KEY"] = ""  # empty means "no key": explain() uses fallback text
    saved = {name: os.environ.get(name) for name in wanted}
    os.environ.update(wanted)
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@contextmanager
def in_process_api() -> Iterator[Getter]:
    """Call the FastAPI app directly, without a server. Fast; used by pytest."""
    from fastapi.testclient import TestClient

    from .api import app

    with TestClient(app) as client:
        def get(path: str, params: dict | None = None) -> tuple[int, Any]:
            response = client.get(path, params=params)
            return response.status_code, _json_or_none(response)
        yield get


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def live_api(startup_timeout_s: float = 30.0) -> Iterator[Getter]:
    """Start a real uvicorn server on a free port and talk to it over HTTP."""
    import requests

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    # The server inherits os.environ, which api_env() has already pointed at our files.
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "earth_system_trend.api:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
    )
    try:
        deadline = time.monotonic() + startup_timeout_s
        while True:
            if server.poll() is not None:
                raise E2EError(f"uvicorn exited with code {server.returncode} before it was ready")
            try:
                if requests.get(base + "/health", timeout=2).status_code == 200:
                    break
            except requests.RequestException:
                pass
            if time.monotonic() > deadline:
                raise E2EError(f"uvicorn did not answer /health within {startup_timeout_s:.0f} s")
            time.sleep(0.2)
        logger.info("live API running at %s", base)

        def get(path: str, params: dict | None = None) -> tuple[int, Any]:
            response = requests.get(base + path, params=params, timeout=30)
            return response.status_code, _json_or_none(response)
        yield get
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()


def _json_or_none(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


# --- 3. schema checks ---------------------------------------------------------------


class CheckFailed(AssertionError):
    """One check found a problem. The message says what."""


@dataclass
class Report:
    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed and bool(self.passed)

    def check(self, name: str, test: Callable[[], None]) -> None:
        """Run one check and record PASS or FAIL. A failure never stops the other checks."""
        try:
            test()
        except (CheckFailed, ValidationError) as exc:
            self.failed.append((name, str(exc)))
            logger.error("FAIL  %s\n%s", name, _indent(str(exc)))
        else:
            self.passed.append(name)
            logger.info("PASS  %s", name)


def _indent(text: str) -> str:
    return "\n".join("        " + line for line in text.splitlines())


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailed(message)


def fetch(get: Getter, path: str, model: type[BaseModel], params: dict | None = None) -> Any:
    """GET path, expect 200, and validate the body against model (unknown fields fail)."""
    status, body = get(path, params)
    expect(status == 200, f"GET {path} {params or ''} answered HTTP {status}: {body}")
    return model.model_validate(body)


def check_series_rules(where: str, period: Any, series: list[SeriesPoint]) -> None:
    """The contract's rules: oldest first, one entry per month, period matches the ends."""
    expect(series[0].date == period.start,
           f"{where}: period.start {period.start} but the series starts {series[0].date}")
    expect(series[-1].date == period.end,
           f"{where}: period.end {period.end} but the series ends {series[-1].date}")
    for before, after in pairwise(series):
        expect(after.date == next_month(before.date),
               f"{where}: {before.date} is followed by {after.date}, not the next month")


def check_trend_rules(where: str, trend: Any) -> None:
    """The trend fields agree with each other, as pymannkendall defines them."""
    significant = trend.p < SIGNIFICANCE_LEVEL
    expect(significant == (trend.trend != "no trend"),
           f"{where}: p={trend.p} but trend is {trend.trend!r}")
    if trend.trend == "increasing":
        expect(trend.tau > 0, f"{where}: 'increasing' but tau={trend.tau}")
    if trend.trend == "decreasing":
        expect(trend.tau < 0, f"{where}: 'decreasing' but tau={trend.tau}")


def check_matches_file(where: str, answer: BaseModel, expected: Results) -> None:
    """Every field the answer shares with the results file has the same value."""
    want = expected.model_dump()
    for name, value in answer.model_dump().items():
        if name in want:
            expect(value == want[name], f"{where}: '{name}' differs from the pipeline's file")


def run_checks(get: Getter, built: Built) -> Report:
    """Ask the API every endpoint and check each answer. Returns the report."""
    report = Report()
    main = load_results(built.results_path)  # what the pipeline wrote; the API must match it
    main_id = slugify(main.region)
    sub = {region_id: load_results(built.regions_dir / f"{region_id}.json")
           for region_id in built.region_ids}
    every = {main_id: main, **sub}

    report.check("/health is ok", lambda: fetch(get, "/health", Health))

    def results_endpoint() -> None:
        answer = fetch(get, "/results", Results)
        expect(answer == main, "/results differs from the results.json the pipeline wrote")
        check_series_rules("/results", answer.period, answer.series)
        check_trend_rules("/results", answer.trend)
    report.check("/results matches the contract and the pipeline output", results_endpoint)

    def regions_endpoint() -> None:
        answer = fetch(get, "/regions", RegionsResponse)
        ids = [entry.id for entry in answer.regions]
        # The API lists the whole study area first, then sub-region files sorted by id.
        want = [main_id, *sorted(built.region_ids)]
        expect(ids == want, f"/regions ids are {ids}, expected {want}")
        for entry in answer.regions:
            check_matches_file(f"/regions[{entry.id}]", entry, every[entry.id])
    report.check("/regions lists the study area and every sub-region", regions_endpoint)

    for region_id, expected in every.items():
        def series_endpoint(region_id: str = region_id, expected: Results = expected) -> None:
            answer = fetch(get, "/series", SeriesResponse, {"region": region_id})
            check_matches_file(f"/series?region={region_id}", answer, expected)
            check_series_rules(f"/series?region={region_id}", answer.period, answer.series)
        report.check(f"/series?region={region_id}", series_endpoint)

        def trend_endpoint(region_id: str = region_id, expected: Results = expected) -> None:
            answer = fetch(get, "/trend", TrendResponse, {"region": region_id})
            check_matches_file(f"/trend?region={region_id}", answer, expected)
            check_trend_rules(f"/trend?region={region_id}", answer.trend)
            expect(bool(answer.explanation and answer.explanation.strip()),
                   f"/trend?region={region_id}: explanation is empty")
        report.check(f"/trend?region={region_id}", trend_endpoint)

    def default_trend() -> None:
        answer = fetch(get, "/trend", TrendResponse)
        check_matches_file("/trend", answer, main)
    report.check("/trend without ?region= is the study area", default_trend)

    def unknown_region() -> None:
        for path in ("/series", "/trend"):
            status, body = get(path, {"region": UNKNOWN_REGION})
            expect(status == 404, f"{path}?region={UNKNOWN_REGION} answered HTTP {status}, not 404")
            expect(isinstance(body, dict) and isinstance(body.get("detail"), str),
                   f"{path}: 404 body has no 'detail' message: {body}")
    report.check("unknown region answers 404 with a message", unknown_region)

    return report


# --- putting it together --------------------------------------------------------------


def run_e2e(workdir: Path, *, stub: bool = False, live: bool = False, with_ai: bool = False,
            csv: Path = Path(DEFAULT_SERIES_CSV),
            regions_file: Path = Path(DEFAULT_REGIONS_FILE)) -> Report:
    """Pipeline -> API -> checks, all inside workdir. Raises E2EError if setup fails."""
    if stub:
        csv, regions_file = write_stub_inputs(workdir / "inputs")
    placeholder = Built(workdir / "results" / "results.json",
                        workdir / "results" / "regions", [])
    # The env is set before the pipeline runs too, so its explain step sees the same settings.
    with api_env(placeholder, workdir / "explain_cache.json", with_ai):
        logger.info("=== 1/3 pipeline (%s inputs)", "fake" if stub else "Data layer")
        built = build(workdir, csv, regions_file)
        logger.info("=== 2/3 API (%s)", "live uvicorn server" if live else "in-process")
        with (live_api() if live else in_process_api()) as get:
            logger.info("=== 3/3 schema checks")
            return run_checks(get, built)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end test: pipeline -> API -> schema checks.")
    parser.add_argument("--stub", action="store_true",
                        help="use fake CSVs instead of the Data layer's")
    parser.add_argument("--live", action="store_true",
                        help="start a real uvicorn server instead of calling the app in-process")
    parser.add_argument("--with-ai", action="store_true",
                        help="let the explain step use OPENAI_API_KEY (costs money)")
    parser.add_argument("--csv", type=Path, default=Path(DEFAULT_SERIES_CSV),
                        help="the study area's date,value CSV; sub-region CSVs sit next to it")
    parser.add_argument("--regions-file", type=Path, default=Path(DEFAULT_REGIONS_FILE))
    parser.add_argument("--keep", type=Path, default=None,
                        help="write into this folder and keep it, instead of a temp folder")
    args = parser.parse_args(argv)

    configure_logging()
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise here
    try:
        if args.keep:
            args.keep.mkdir(parents=True, exist_ok=True)
            report = run_e2e(args.keep, stub=args.stub, live=args.live, with_ai=args.with_ai,
                             csv=args.csv, regions_file=args.regions_file)
        else:
            with tempfile.TemporaryDirectory(prefix="esd-e2e-") as folder:
                report = run_e2e(Path(folder), stub=args.stub, live=args.live,
                                 with_ai=args.with_ai, csv=args.csv,
                                 regions_file=args.regions_file)
    except E2EError as exc:
        logger.error("e2e setup failed: %s", exc)
        return 1

    total = len(report.passed) + len(report.failed)
    if report.ok:
        logger.info("e2e passed: %d/%d checks", total, total)
        return 0
    logger.error("e2e FAILED: %d of %d checks failed: %s", len(report.failed), total,
                 ", ".join(name for name, _ in report.failed))
    return 1


if __name__ == "__main__":
    sys.exit(main())