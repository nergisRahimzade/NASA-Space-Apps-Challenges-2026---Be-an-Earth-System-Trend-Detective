import plotly.graph_objects as go

# Placeholder colors from docs/design_notes.md. The real theme comes on Day 6.
COOLING_COLOR = "#3B82C4"
NEUTRAL_COLOR = "#F2F2F2"
WARMING_COLOR = "#E4572E"


def make_map(points, units):
    """Scatter map of per-location trends. Each point is {name, lat, lon, slope}."""
    # A symmetric range puts zero exactly at the neutral middle of the scale.
    limit = max(abs(p["slope"]) for p in points)

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
                    [0, COOLING_COLOR],
                    [0.5, NEUTRAL_COLOR],
                    [1, WARMING_COLOR],
                ],
                "cmin": -limit,
                "cmax": limit,
                "line": {"width": 1, "color": "#444444"},
                "colorbar": {
                    "title": {"text": f"Trend ({units} per month)"},
                    "tickvals": [-limit, 0, limit],
                    "ticktext": [
                        f"Cooling (-{limit:.2f})",
                        "0",
                        f"Warming (+{limit:.2f})",
                    ],
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
        landcolor="#B8BEC8",
        showcoastlines=True,
        coastlinecolor="#6B7280",
        showcountries=True,
        countrycolor="#6B7280",
        showsubunits=True,
        subunitcolor="#8A94A6",
        bgcolor="rgba(0,0,0,0)",
    )
    fig.update_layout(height=420, margin={"l": 0, "r": 0, "t": 10, "b": 0})
    return fig