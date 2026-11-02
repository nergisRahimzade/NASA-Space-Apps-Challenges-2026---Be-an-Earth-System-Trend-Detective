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

DEFAULT_RESULTS_PATH = "results.mock.json"
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_S = 15.0
DEFAULT_CACHE_PATH = "data/cache/explanations.json"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True)
class Settings:
    """A read-only bundle of settings. Build one with get_settings()."""

    results_path: Path
    openai_api_key: str | None
    openai_model: str
    openai_timeout_s: float
    explain_cache_path: Path
    log_level: str


def get_settings() -> Settings:
    """Read the environment now and return the current settings.

    This is a function, not a module-level constant, so a changed variable
    (for example in a test) is picked up on the next call.
    """
    return Settings(
        results_path=Path(os.getenv("RESULTS_PATH", DEFAULT_RESULTS_PATH)),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
        openai_timeout_s=_env_float("OPENAI_TIMEOUT_S", DEFAULT_TIMEOUT_S),
        explain_cache_path=Path(os.getenv("EXPLAIN_CACHE_PATH", DEFAULT_CACHE_PATH)),
        log_level=(os.getenv("LOG_LEVEL") or DEFAULT_LOG_LEVEL).upper(),
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
