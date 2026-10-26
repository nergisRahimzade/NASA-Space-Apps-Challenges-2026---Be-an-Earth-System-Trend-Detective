import math


def mock_points():
    """Made-up per-location trends so the map can be built before real data exists.

    This is NOT part of the contract. The coordinates are arbitrary placeholders.
    Replace this once the team defines what the map receives (ESD-D13-BE, /map).
    """
    points = []
    for i in range(5):
        for j in range(6):
            slope = 0.03 * math.sin(i * 1.3) + 0.02 * math.cos(j * 0.9) + 0.01
            points.append(
                {
                    "name": f"Point {i * 6 + j + 1}",
                    "lat": 30 + 2 * i,
                    "lon": -120 + 4 * j,
                    "slope": round(slope, 4),
                }
            )
    return points