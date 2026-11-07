"""Find every results file the API can serve: the whole study area plus sub-regions.

ESD-D12-BE. The whole study area lives in the main results file
(results/results.json, or results.mock.json in mock mode). Each sub-region
has its own file in the regions folder (results/regions/<id>.json), in the
same contract shape. The file name is the region's id, for example
phoenix_northwest.json; the region's label is the "region" field inside it.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .contract import ContractError, Results, load_results

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionResults:
    id: str  # short name used in URLs, e.g. "phoenix_northwest"
    results: Results  # the whole results file for that region


def slugify(label: str) -> str:
    """'Phoenix study area' -> 'phoenix_study_area'."""
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")


def load_region_files(regions_dir: Path | None) -> list[RegionResults]:
    """Every valid <id>.json in the regions folder, sorted by id.

    A file that breaks the contract is skipped with a warning, so one bad
    region cannot take the whole /regions list down.
    """
    if regions_dir is None or not regions_dir.is_dir():
        return []
    found = []
    for path in sorted(regions_dir.glob("*.json")):
        try:
            found.append(RegionResults(id=path.stem, results=load_results(path)))
        except ContractError as exc:
            logger.warning("Skipping region file that breaks the contract: %s", exc)
    return found


def matches(entry: RegionResults, wanted: str) -> bool:
    """True if wanted is the region's id or its label, ignoring upper/lowercase."""
    wanted = wanted.strip().casefold()
    return wanted in {entry.id.casefold(), entry.results.region.strip().casefold()}
