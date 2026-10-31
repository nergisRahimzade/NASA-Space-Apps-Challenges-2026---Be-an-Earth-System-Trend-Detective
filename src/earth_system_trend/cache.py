"""A small file-based cache for AI explanations.

ESD-D04-BE. Each answer is saved in a JSON file under a fingerprint (a hash)
of the exact input that produced it. Asking again with the same input reads
the saved answer instead of calling the API, which saves time and money.

The cache is only an optimization: a missing, damaged or unwritable cache
file never raises, it just behaves like an empty cache.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def make_key(data: Any) -> str:
    """Return a SHA-256 fingerprint of data.

    sort_keys=True makes {"a": 1, "b": 2} and {"b": 2, "a": 1} produce the same key.
    """
    text = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cache_get(path: Path, key: str) -> str | None:
    """Return the saved answer for key, or None if there isn't one."""
    value = _load(path).get(key)
    return value if isinstance(value, str) else None


def cache_put(path: Path, key: str, value: str) -> None:
    """Save value under key. Logs and carries on if the file can't be written."""
    data = _load(path)
    data[key] = value
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)  # swap in the new file in one step
    except OSError as exc:
        logger.warning("Could not write explanation cache %s: %s", path, exc)


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable explanation cache %s: %s", path, exc)
        return {}
    return data if isinstance(data, dict) else {}
