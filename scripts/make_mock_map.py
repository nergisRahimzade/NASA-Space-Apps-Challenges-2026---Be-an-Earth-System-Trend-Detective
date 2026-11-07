"""Write trend_map.mock.json: made-up per-cell trends in the map contract shape.

ESD-D13-BE. The cells sit on the real Phoenix grid (0.05°, 12 x 16 cells) so
the map looks the way the real one will, but every number is invented.
Run from the project root:

    uv run --locked python scripts/make_mock_map.py
"""

import json
import math
from pathlib import Path

WEST, SOUTH, STEP = -112.4, 33.2, 0.05
ROWS, COLS = 12, 16


def mock_map() -> dict:
    points = []
    for row in range(ROWS):
        for col in range(COLS):
            lat = round(SOUTH + STEP * (row + 0.5), 3)
            lon = round(WEST + STEP * (col + 0.5), 3)
            if (row, col) in {(0, 0), (11, 15)}:  # two cells with too little data
                points.append({"lat": lat, "lon": lon, "slope": None,
                               "p": None, "tau": None, "trend": None})
                continue
            # A warm patch near the middle, cooling toward one corner.
            distance = math.hypot(row - 6, col - 9) / 9
            slope = round(0.032 * (1 - distance) - 0.014 + 0.004 * math.sin(row * col), 4)
            p = round(min(1.0, 0.001 + 0.6 * (1 - min(1.0, abs(slope) / 0.01))), 4)
            significant = p < 0.05
            trend = ("increasing" if slope > 0 else "decreasing") if significant else "no trend"
            tau = round(max(-1.0, min(1.0, slope * 12)), 3)
            points.append({"lat": lat, "lon": lon, "slope": slope,
                           "p": p, "tau": tau, "trend": trend})
    return {
        "region": "Example Region",
        "variable": "Surface air temperature",
        "units": "°C",
        "period": {"start": "2003-01", "end": "2003-06"},
        "test": "Mann-Kendall (made-up mock numbers)",
        "resolution_deg": STEP,
        "points": points,
    }


if __name__ == "__main__":
    target = Path("trend_map.mock.json")
    target.write_text(json.dumps(mock_map(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target} with {ROWS * COLS} cells.")