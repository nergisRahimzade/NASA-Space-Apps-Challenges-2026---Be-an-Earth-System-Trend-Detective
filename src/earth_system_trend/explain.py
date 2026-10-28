"""Safe wrapper around the OpenAI call that turns a trend result into plain words.

ESD-D03-BE. Rules:
- The API key comes from the environment (OPENAI_API_KEY), never from code.
- Each call has a timeout; transient failures get exactly one retry.
- explain() never raises. On any failure it returns fallback text built only
  from the numbers in the result, so the dashboard always has something to show.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import openai

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TIMEOUT_S = 15.0
MAX_ATTEMPTS = 2  # first try + 1 retry
RETRY_DELAY_S = 1.0
SIGNIFICANCE_LEVEL = 0.05

# Placeholder until ESD-D04-AI commits src/prompts/explain_v1.txt.
SYSTEM_PROMPT = (
    "You explain climate trend statistics to a general audience. "
    "Use only the numbers given in the input JSON. "
    f"Say whether the trend is statistically significant (p < {SIGNIFICANCE_LEVEL}). "
    "Never invent causes or numbers. Reply in at most 120 words."
)

# Errors worth one more try. Auth / bad-request errors are not retried.
TRANSIENT_ERRORS = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def explain(
    result: dict[str, Any],
    *,
    client: Any | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> str:
    """Return a plain-language explanation of a results.json-shaped dict.

    `client` can be injected (tests pass a mock). Otherwise one is built from
    environment variables. This function never raises.
    """
    model = model or os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    timeout = timeout if timeout is not None else _env_float(
        "OPENAI_TIMEOUT_S", DEFAULT_TIMEOUT_S
    )

    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set; using fallback text.")
            return fallback_text(result)
        # SDK retries disabled so our own retry policy is the only one.
        client = openai.OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(result, default=str)},
    ]

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.chat.completions.create(
                model=model, messages=messages, timeout=timeout
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text
            logger.warning("Empty reply from model (attempt %d).", attempt)
        except TRANSIENT_ERRORS as exc:
            logger.warning("Transient AI error (attempt %d): %s", attempt, exc)
        except Exception as exc:  # noqa: BLE001 - must never raise
            logger.error("Non-retryable AI error: %s", exc)
            break
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_S)

    return fallback_text(result)


def fallback_text(result: dict[str, Any]) -> str:
    """Deterministic summary using only numbers present in `result`."""
    trend = result.get("trend") or {}
    region = result.get("region") or "the selected region"
    period = result.get("period")
    direction = trend.get("trend")
    slope = trend.get("slope")
    p = trend.get("p")

    where = f"{region} ({period})" if period else str(region)
    if direction is None or p is None:
        return (
            f"An automatic explanation is unavailable for {where}, "
            "and there is not enough trend information to summarize it."
        )

    parts = [f"For {where}, the Mann-Kendall test reports: {direction}."]
    if slope is not None:
        parts.append(f"Slope: {slope}.")
    significant = _is_number(p) and p < SIGNIFICANCE_LEVEL
    verdict = "statistically significant" if significant else "not statistically significant"
    parts.append(f"p-value: {p}, which is {verdict} at p < {SIGNIFICANCE_LEVEL}.")
    parts.append("(Automatic AI explanation unavailable; showing a summary.)")
    return " ".join(parts)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default