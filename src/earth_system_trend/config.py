"""Every setting the backend reads, in one place.

ESD-D04-BE. Values come from environment variables. For local work, copy
.env.example to .env in the project root and fill it in; .env is git-ignored,
so secrets like the OpenAI key never reach GitHub. On a server, set the same
variables in the host's dashboard instead.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Copy values from a local .env file into the environment. Values that are
# already set (for example on the live server) are never overwritten.
load_dotenv()

DEFAULT_MAP_PATH = "trend_map.mock.json"  # fake per-cell trends (ESD-D13-BE)
REAL_MAP_PATH = "results/trend_map.json"  # what the Data layer's trend map step writes
DEFAULT_RESULTS_PATH = "results.mock.json"  # the fake results everyone builds against
REAL_RESULTS_PATH = "results/results.json"  # what the pipeline writes
DEFAULT_SERIES_CSV = "data/processed/timeseries.csv"  # the Data layer's monthly series
REAL_REGIONS_DIR = "results/regions"  # one results file per sub-region (ESD-D12-BE)
DEFAULT_REGIONS_FILE = "docs/subregions.json"  # the Data layer's list of sub-regions
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_CACHE_PATH = "data/cache/explanations.json"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_CORS_ORIGINS = "http://localhost:8501"
DEFAULT_RATE_LIMIT_PER_MINUTE = 60


@dataclass(frozen=True)
class Settings:
    """A read-only bundle of settings. Build one with get_settings()."""

    results_path: Path
    use_mock: bool
    series_csv_path: Path
    regions_dir: Path | None
    regions_file: Path
    map_path: Path
    openai_api_key: str | None
    openai_model: str
    openai_timeout_s: float
    explain_cache_path: Path
    log_level: str
    cors_origins: list[str]
    rate_limit_per_minute: int


def get_settings() -> Settings:
    """Read the environment now and return the current settings.

    This is a function, not a module-level constant, so a changed variable
    (for example in a test) is picked up on the next call.
    """
    use_mock = _env_bool("USE_MOCK", True)
    default_results = DEFAULT_RESULTS_PATH if use_mock else REAL_RESULTS_PATH
    return Settings(
        # RESULTS_PATH, if set, always wins; otherwise USE_MOCK picks the file.
        results_path=Path(os.getenv("RESULTS_PATH") or default_results),
        use_mock=use_mock,
        series_csv_path=Path(os.getenv("SERIES_CSV_PATH", DEFAULT_SERIES_CSV)),
        # Sub-regions are real data only, so mock mode has none unless REGIONS_DIR says so.
        regions_dir=_regions_dir(use_mock),
        regions_file=Path(os.getenv("REGIONS_FILE", DEFAULT_REGIONS_FILE)),
        # MAP_PATH, if set, always wins; otherwise USE_MOCK picks the file (ESD-D13-BE).
        map_path=Path(os.getenv("MAP_PATH") or (DEFAULT_MAP_PATH if use_mock else REAL_MAP_PATH)),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        openai_timeout_s=_env_float("OPENAI_TIMEOUT_S", DEFAULT_TIMEOUT_S),
        explain_cache_path=Path(os.getenv("EXPLAIN_CACHE_PATH", DEFAULT_CACHE_PATH)),
        log_level=(os.getenv("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper(),
        cors_origins=_env_list("CORS_ORIGINS", DEFAULT_CORS_ORIGINS),
        rate_limit_per_minute=_env_int("RATE_LIMIT_PER_MINUTE", DEFAULT_RATE_LIMIT_PER_MINUTE),
    )


def configure_logging() -> None:
    """Show log messages with a time, level and source. Safe to call more than once."""
    level = getattr(logging, get_settings().log_level, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _env_float(name: str, default: float) -> float:
    """Read a number from the environment, falling back to default if unset or invalid."""
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Read a whole number from the environment, falling back to default if unset or invalid."""
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


def _env_list(name: str, default: str) -> list[str]:
    """Read a comma-separated list: "a, b,c" becomes ["a", "b", "c"]."""
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _env_bool(name: str, default: bool) -> bool:
    """Read yes/no from the environment: "true", "1", "yes" or "on" mean True."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _regions_dir(use_mock: bool) -> Path | None:
    """REGIONS_DIR if set; otherwise results/regions with real data and none with mock data."""
    raw = os.getenv("REGIONS_DIR")
    if raw:
        return Path(raw)
    return None if use_mock else Path(REAL_REGIONS_DIR)
