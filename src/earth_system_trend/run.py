"""One command that builds results.json from the monthly series.

ESD-D09-BE. Run from the project root:

    uv run --locked python -m earth_system_trend.run           # real data
    uv run --locked python -m earth_system_trend.run --stub    # fake data, for testing
    uv run --locked python -m earth_system_trend.run --force   # rebuild even if up to date
    uv run --locked python -m earth_system_trend.run --all-regions   # every sub-region (ESD-D12-BE)

Steps:
  1. series   read the Data layer's CSV (data/processed/timeseries.csv)
  2. trend    run the trend test on it
  3. explain  ask the AI for a plain-language explanation (fallback text without a key)
  4. results  check everything against the contract and save results/results.json

Downloading and cleaning the NASA files belong to the Data layer; their job
ends when the CSV exists. With --stub and no CSV, step 1 writes a fake CSV
first, so the whole chain can be tried before real data is ready.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path

from .config import REAL_REGIONS_DIR, REAL_RESULTS_PATH, configure_logging, get_settings
from .contract import Period, Results
from .explain import explain
from .timeseries import TimeseriesError, load_timeseries, next_month
from .trend import TrendError, run_trend

logger = logging.getLogger("earth_system_trend.run")

# From docs/data_shortlist.md, the Data layer's chosen study.
DEFAULT_REGION = "Phoenix study area"
DEFAULT_VARIABLE = "Nighttime land surface temperature"
DEFAULT_UNITS = "°C"


class PipelineError(Exception):
    """A problem with the inputs that stops the pipeline. Raised when:

    - the series CSV does not exist and --stub was not given;
    - the CSV is not in the date,value format (wrong columns, a bad date,
      a bad number or a month listed twice);
    - fewer than 24 months have values, or the trend test returns no p-value.

    main() catches it, logs "pipeline failed: <the reason>" and exits with code 1.
    """


def write_stub_series(path: Path, start: str = "2003-01", months: int = 264) -> None:
    """Write a fake but realistic monthly CSV: a seasonal cycle, a slow rise, a few gaps."""
    lines = ["date,value"]
    month = start
    for i in range(months):
        seasonal = 9 * math.sin((i - 3) / 12 * 2 * math.pi)
        value = "" if i in (40, 41, 150) else f"{22 + seasonal + 0.006 * i:.2f}"
        lines.append(f"{month},{value}")
        month = next_month(month)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def is_up_to_date(output: Path, source: Path) -> bool:
    """True if the output exists and is newer than its source."""
    return output.exists() and source.exists() and output.stat().st_mtime >= source.stat().st_mtime


def run_pipeline(csv_path: Path, out_path: Path, region: str, variable: str, units: str,
                 stub: bool = False, force: bool = False) -> Path:
    """Run every step and return the path of the saved results file."""
    if not csv_path.exists():
        if not stub:
            raise PipelineError(
                f"{csv_path} not found. Run the Data steps first, or try --stub for fake data."
            )
        logger.info("step 0/4 stub: writing fake series to %s", csv_path)
        write_stub_series(csv_path)

    if not force and is_up_to_date(out_path, csv_path):
        logger.info("skip: %s is newer than %s (use --force to rebuild)", out_path, csv_path)
        return out_path

    logger.info("step 1/4 series: reading %s", csv_path)
    try:
        series = load_timeseries(csv_path)
    except TimeseriesError as exc:
        raise PipelineError(str(exc)) from exc
    missing = sum(point.value is None for point in series)
    logger.info("         %d months (%s to %s), %d missing",
                len(series), series[0].date, series[-1].date, missing)

    logger.info("step 2/4 trend: Mann-Kendall test")
    try:
        trend = run_trend(series)
    except TrendError as exc:
        raise PipelineError(str(exc)) from exc
    logger.info("         %s, slope=%s per month, p=%s", trend.trend, trend.slope, trend.p)

    logger.info("step 3/4 explain: asking the AI")
    period = Period(start=series[0].date, end=series[-1].date)
    # Only the summary goes to the AI; the 264 monthly values would just cost tokens.
    text = explain({
        "region": region,
        "variable": variable,
        "units": units,
        "period": f"{period.start} to {period.end}",
        "trend": trend.model_dump(),
    })

    logger.info("step 4/4 results: checking the contract and saving %s", out_path)
    results = Results(region=region, variable=variable, units=units, period=period,
                      series=series, trend=trend, explanation=text)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(results.model_dump(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return out_path


def load_region_list(regions_file: Path) -> dict[str, str]:
    """Read the Data layer's sub-region list as {id: label}.

    The file looks like {"regions": {"phoenix_northwest": {"label": "...", ...}, ...}}.
    """
    if not regions_file.exists():
        raise PipelineError(f"{regions_file} not found. It lists the sub-regions (Data layer, D11).")
    try:
        data = json.loads(regions_file.read_text(encoding="utf-8"))
        regions = {region_id: info["label"] for region_id, info in data["regions"].items()}
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise PipelineError(
            f"{regions_file} must look like {{\"regions\": {{\"<id>\": {{\"label\": ...}}}}}}"
        ) from exc
    if not regions:
        raise PipelineError(f"{regions_file} lists no regions")
    return regions


def run_all_regions(regions_file: Path, csv_dir: Path, out_dir: Path, variable: str, units: str,
                    stub: bool = False, force: bool = False) -> list[Path]:
    """ESD-D12-BE. Build one results file per sub-region.

    Region <id> reads <csv_dir>/timeseries_<id>.csv and writes <out_dir>/<id>.json.
    Every region is tried even if one fails; the failures are reported together.
    """
    written, failed = [], []
    for region_id, label in load_region_list(regions_file).items():
        logger.info("=== region %s (%s)", region_id, label)
        try:
            written.append(run_pipeline(csv_dir / f"timeseries_{region_id}.csv",
                                        out_dir / f"{region_id}.json", label, variable, units,
                                        stub=stub, force=force))
        except PipelineError as exc:
            logger.error("region %s failed: %s", region_id, exc)
            failed.append(region_id)
    if failed:
        raise PipelineError(f"{len(failed)} region(s) failed: {', '.join(failed)}")
    return written


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Build results.json from the monthly series.")
    parser.add_argument("--csv", type=Path, default=settings.series_csv_path,
                        help="the Data layer's date,value CSV")
    parser.add_argument("--out", type=Path, default=Path(REAL_RESULTS_PATH),
                        help="where to save the results")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--variable", default=DEFAULT_VARIABLE)
    parser.add_argument("--units", default=DEFAULT_UNITS)
    parser.add_argument("--stub", action="store_true", help="write fake data if the CSV is missing")
    parser.add_argument("--force", action="store_true", help="rebuild even if up to date")
    parser.add_argument("--all-regions", action="store_true",
                        help="build results/regions/<id>.json for every sub-region instead")
    parser.add_argument("--regions-file", type=Path, default=settings.regions_file,
                        help="the Data layer's sub-region list")
    parser.add_argument("--regions-out", type=Path, default=Path(REAL_REGIONS_DIR),
                        help="folder for the per-region results files")
    args = parser.parse_args(argv)

    configure_logging()
    try:
        if args.all_regions:
            paths = run_all_regions(args.regions_file, args.csv.parent, args.regions_out,
                                    args.variable, args.units, stub=args.stub, force=args.force)
            logger.info("done: %d region files in %s", len(paths), args.regions_out)
        else:
            path = run_pipeline(args.csv, args.out, args.region, args.variable, args.units,
                                stub=args.stub, force=args.force)
            logger.info("done: %s (serve it with USE_MOCK=false)", path)
    except PipelineError as exc:
        logger.error("pipeline failed: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
