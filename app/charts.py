from datetime import datetime
from statistics import median

import plotly.graph_objects as go

# Placeholder colors until the theme file (Day 6) and the color-blind check (Day 17).
VALUES_COLOR = "#3B82C4"
TREND_COLOR = "#F2B84B"


def month_numbers(dates):
    """Turn ['2003-01', '2003-02', ...] into datetimes plus months since the first one."""
    parsed = [datetime.strptime(d, "%Y-%m") for d in dates]
    first = parsed[0]
    months = [(d.year - first.year) * 12 + (d.month - first.month) for d in parsed]
    return parsed, months


def trend_values(months, values, slope, intercept=None):
    """Points of a straight line with the given slope (change per month).

    A slope alone doesn't say where the line sits, so use the contract's
    intercept if there is one. Otherwise anchor the line at the median point,
    which is how Sen's slope defines its intercept (as far as I know).
    """
    if intercept is None:
        intercept = median(values) - slope * median(months)
    return [intercept + slope * m for m in months]


def make_chart(v):
    dates, months = month_numbers(v["dates"])
    line = trend_values(months, v["values"], v["slope"], v.get("intercept"))
    units = v["units"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=v["values"],
            mode="lines+markers",
            name="Monthly values",
            line={"color": VALUES_COLOR},
            hovertemplate="%{x|%b %Y}<br>Value: %{y:.1f} " + units + "<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=line,
            mode="lines",
            name="Trend line",
            line={"color": TREND_COLOR, "dash": "dash"},
            hovertemplate="%{x|%b %Y}<br>Trend: %{y:.2f} " + units + "<extra></extra>",
        )
    )
    fig.update_layout(
        height=340,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        xaxis_title="Month",
        yaxis_title=f"{v['variable']} ({units})",
        legend={"orientation": "h", "y": 1.12, "x": 0},
    )
    return fig