import plotly.graph_objects as go
from theme import (
    BACKGROUND,
    COOLING,
    MAP_LAND,
    MAP_LINES,
    NEUTRAL,
    WARMING,
    style_figure,
)


def make_map(points, units):
    """Scatter map of per-location trends. Each point is {name, lat, lon, slope}."""
    # A symmetric range puts zero exactly at the neutral middle of the scale.
    limit = max(abs(p["slope"]) for p in points) or 1

    fig = go.Figure(
        go.Scattergeo(
            lat=[p["lat"] for p in points],
            lon=[p["lon"] for p in points],
            text=[p["name"] for p in points],
            customdata=[p["slope"] for p in points],
            mode="markers",
            marker={
                "size": 16,
                "color": [p["slope"] for p in points],
                "colorscale": [
                    [0, COOLING],
                    [0.5, NEUTRAL],
                    [1, WARMING],
                ],
                "cmin": -limit,
                "cmax": limit,
                "line": {"width": 1, "color": BACKGROUND},
                "colorbar": {
                    "title": {"text": f"Trend ({units} per month)", "side": "right"},
                    "tickvals": [-limit, 0, limit],
                    "ticktext": [
                        f"Cooling (-{limit:.2f})",
                        "0",
                        f"Warming (+{limit:.2f})",
                    ],
                    "outlinewidth": 0,
                },
            },
            hovertemplate=(
                "%{text}<br>Trend: %{customdata:+.3f} " + units + " per month"
                "<extra></extra>"
            ),
        )
    )
    fig.update_geos(
        fitbounds="locations",
        showland=True,
        landcolor=MAP_LAND,
        showcoastlines=True,
        coastlinecolor=MAP_LINES,
        showcountries=True,
        countrycolor=MAP_LINES,
        showsubunits=True,
        subunitcolor=MAP_LINES,
        showlakes=False,
        bgcolor="rgba(0,0,0,0)",
    )
    style_figure(fig, 420)
    return fig