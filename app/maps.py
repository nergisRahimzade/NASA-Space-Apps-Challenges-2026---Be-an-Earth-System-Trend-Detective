import plotly.graph_objects as go
from components import format_p  # add to the imports at the top
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
    """Scatter map of per-location trends. Each point is {name, lat, lon, slope, p?}."""
    points = [p for p in points if p.get("slope") is not None]
    # A symmetric range puts zero exactly at the neutral middle of the scale.
    limit = max(abs(p["slope"]) for p in points) or 1
    # Smaller dots when there are many points, so they don't hide each other.
    size = 16 if len(points) <= 60 else 9 if len(points) <= 500 else 5
    has_p = any(p.get("p") is not None for p in points)

    hover = "%{text}<br>Trend: %{customdata[0]:+.4f} " + units + " per month"
    if has_p:
        hover += "<br>p-value: %{customdata[1]}"
    hover += "<extra></extra>"

    fig = go.Figure(
        go.Scattergeo(
            lat=[p["lat"] for p in points],
            lon=[p["lon"] for p in points],
            text=[p["name"] for p in points],
            customdata=[[p["slope"], format_p(p.get("p"))] for p in points],
            mode="markers",
            marker={
                "size": size,
                "color": [p["slope"] for p in points],
                "colorscale": [[0, COOLING], [0.5, NEUTRAL], [1, WARMING]],
                "cmin": -limit,
                "cmax": limit,
                "line": {"width": 0.5 if size < 16 else 1, "color": BACKGROUND},
                "colorbar": {
                    "title": {"text": f"Trend ({units} per month)", "side": "right"},
                    "tickvals": [-limit, 0, limit],
                    "ticktext": [
                        f"Cooling (-{limit:.3g})",
                        "0",
                        f"Warming (+{limit:.3g})",
                    ],
                    "outlinewidth": 0,
                },
            },
            hovertemplate=hover,
        )
    )
    # (keep your existing fig.update_geos(...) block and style_figure(fig, 420) as-is)
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