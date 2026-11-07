from datetime import datetime
from statistics import median

import plotly.graph_objects as go
from components import is_significant
from theme import ACCENT, BORDER, MUTED, NEUTRAL, TEXT, style_figure

# The trend line in the anomaly view stays hidden until the team confirms which
# series (raw or anomaly) the slope in the results is computed on.
SHOW_TREND_ON_ANOMALY = False


def month_numbers(dates):
    """Turn ['2003-01', '2003-02', ...] into datetimes plus months since the first one."""
    parsed = [datetime.strptime(d, "%Y-%m") for d in dates]
    first = parsed[0]
    months = [(d.year - first.year) * 12 + (d.month - first.month) for d in parsed]
    return parsed, months


def _by_month(parsed, values):
    """Known values grouped by calendar month number (1 to 12)."""
    groups = {}
    for d, v in zip(parsed, values):
        if v is not None:
            groups.setdefault(d.month, []).append(v)
    return groups


def anomaly_available(dates, values):
    """True if some calendar month appears at least twice (so an average means something)."""
    parsed = [datetime.strptime(d, "%Y-%m") for d in dates]
    return any(len(vs) >= 2 for vs in _by_month(parsed, values).values())


def monthly_anomalies(parsed, values):
    """Value minus the average of the same calendar month over the whole period.

    BASELINE: the whole period. If the team picks a fixed reference period
    instead, only this function changes. A month seen just once has no
    anomaly (None), and missing values stay missing.
    """
    groups = _by_month(parsed, values)
    result = []
    for d, v in zip(parsed, values):
        same = groups.get(d.month, [])
        if v is None or len(same) < 2:
            result.append(None)
        else:
            result.append(v - sum(same) / len(same))
    return result


def chart_title(mode):
    """Heading shown above the chart for the chosen view."""
    return "Line chart: anomaly" if mode == "anomaly" else "Line chart: raw values"


def trend_values(months, values, slope, intercept=None):
    """Points of a straight line with the given slope (change per month).

    Months with missing values (None) are ignored when anchoring the line.
    A slope alone doesn't say where the line sits, so use the contract's
    intercept if there is one. Otherwise anchor at the median of known points.
    """
    if intercept is None:
        known = [(m, v) for m, v in zip(months, values) if v is not None]
        if not known:
            return [None] * len(months)
        mid_value = median([v for _, v in known])
        mid_month = median([m for m, _ in known])
        intercept = mid_value - slope * mid_month
    return [intercept + slope * m for m in months]


def make_chart(v, mode="raw"):
    """Line chart of the series. mode is "raw" or "anomaly"."""
    dates, months = month_numbers(v["dates"])
    units = v["units"]
    anomaly = mode == "anomaly"
    values = monthly_anomalies(dates, v["values"]) if anomaly else v["values"]
    series_name = "Monthly anomaly" if anomaly else "Monthly values"
    value_label = "Anomaly" if anomaly else "Value"
    value_format = "%{y:+.2f}" if anomaly else "%{y:.1f}"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines+markers" if len(dates) <= 36 else "lines",
            name=series_name,
            line={"color": NEUTRAL},
            hovertemplate="%{x|%b %Y}<br>"
            + value_label
            + ": "
            + value_format
            + " "
            + units
            + "<extra></extra>",
        )
    )
    # Only draw a trend line when we have a slope for exactly this series.
    show_trend = v.get("slope") is not None and (not anomaly or SHOW_TREND_ON_ANOMALY)
    if show_trend:
        intercept = None if anomaly else v.get("intercept")
        line = trend_values(months, values, v["slope"], intercept)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=line,
                mode="lines",
                name="Trend line",
                line={"color": ACCENT, "dash": "dash"},
                hovertemplate="%{x|%b %Y}<br>Trend: %{y:.2f} "
                + units
                + "<extra></extra>",
            )
        )
    if anomaly:
        fig.add_hline(y=0, line_width=1, line_color=MUTED)
    style_figure(fig, 340)
    y_title = f"Anomaly ({units})" if anomaly else f"{v['variable']} ({units})"
    fig.update_xaxes(title_text="Month", gridcolor=BORDER, linecolor=BORDER)
    fig.update_yaxes(
        title_text=y_title,
        gridcolor=BORDER,
        linecolor=BORDER,
        zerolinecolor=BORDER,
    )
    fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0})
    return fig



def make_region_comparison(regions, units, selected=None):
    """Bar chart of slope per region. Significant bars are gold, the rest grey.

    regions: list of {"name", "slope", "p", "trend"} dicts.
    selected: the region name to outline, or None.
    """
    names = [r["name"] for r in regions]
    slopes = [r["slope"] for r in regions]
    sig = [is_significant(r["p"], r.get("trend")) for r in regions]
    colors = [ACCENT if s else MUTED for s in sig]
    labels = [
        "Significant" if s else "Not significant" if s is False else "No p-value"
        for s in sig
    ]
    outline = [3 if n == selected else 0 for n in names]

    fig = go.Figure(
        go.Bar(
            x=names,
            y=slopes,
            marker={
                "color": colors,
                "line": {"width": outline, "color": TEXT},
            },
            customdata=labels,
            hovertemplate="%{x}<br>Slope: %{y:+.4f} " + units
            + " per month<br>%{customdata}<extra></extra>",
        )
    )
    fig.add_hline(y=0, line_width=1, line_color=MUTED)
    style_figure(fig, 340)
    fig.update_xaxes(title_text="Region", gridcolor=BORDER, linecolor=BORDER)
    fig.update_yaxes(
        title_text=f"Slope ({units} per month)",
        gridcolor=BORDER,
        linecolor=BORDER,
    )
    return fig