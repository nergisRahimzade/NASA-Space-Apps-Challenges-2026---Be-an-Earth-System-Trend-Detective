from datetime import datetime
from statistics import median

import plotly.graph_objects as go
from theme import ACCENT, BORDER, NEUTRAL, style_figure


def month_numbers(dates):
    """Turn ['2003-01', '2003-02', ...] into datetimes plus months since the first one."""
    parsed = [datetime.strptime(d, "%Y-%m") for d in dates]
    first = parsed[0]
    months = [(d.year - first.year) * 12 + (d.month - first.month) for d in parsed]
    return parsed, months


def trend_values(months, values, slope, intercept=None):
    """Points of a straight line with the given slope (change per month).

    A slope alone doesn't say where the line sits, so use the contract's
    intercept if there is one. Otherwise anchor the line at the median point.
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
            line={"color": NEUTRAL},
            hovertemplate="%{x|%b %Y}<br>Value: %{y:.1f} " + units + "<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=line,
            mode="lines",
            name="Trend line",
            line={"color": ACCENT, "dash": "dash"},
            hovertemplate="%{x|%b %Y}<br>Trend: %{y:.2f} " + units + "<extra></extra>",
        )
    )
    style_figure(fig, 340)
    fig.update_xaxes(title_text="Month", gridcolor=BORDER, linecolor=BORDER)
    fig.update_yaxes(
        title_text=f"{v['variable']} ({units})",
        gridcolor=BORDER,
        linecolor=BORDER,
        zerolinecolor=BORDER,
    )
    fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0})
    return fig