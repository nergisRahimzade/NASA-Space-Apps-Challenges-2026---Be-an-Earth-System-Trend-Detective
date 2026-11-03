import streamlit as st
from charts import anomaly_available, chart_title, make_chart
from components import empty_state, error_state, stat_card
from maps import make_map
from mock_map import mock_points
from theme import apply_theme

from api_client import (
    API_URL,
    NoSeriesError,
    load_choices,
    load_results,
    load_series,
)

st.set_page_config(
    page_title="Earth System Trend Detective",
    page_icon="🛰️",
    layout="wide",
)
apply_theme()


@st.cache_data(ttl=60)
def get_results():
    return load_results()


@st.cache_data(ttl=60)
def get_choices(default_region, default_variable):
    return load_choices(default_region, default_variable)


@st.cache_data(ttl=60)
def get_series(region, variable, default_units):
    return load_series(region, variable, default_units)


# The only place that knows the contract's key names.
# If results.mock.json changes, update the keys here and nowhere else.
def to_view(r):
    trend = r["trend"]
    points = r["series"]
    return {
        "region": r["region"],
        "variable": r.get("variable", "[variable]"),
        "start": r["period"]["start"],
        "end": r["period"]["end"],
        "units": r.get("units", "[unit]"),
        "dates": [pt["date"] for pt in points],
        "values": [pt["value"] for pt in points],
        "slope": trend["slope"],
        "intercept": trend.get("intercept"),
        "p": trend["p"],
        "tau": trend["tau"],
        "trend": trend["trend"],
        "significant": trend["p"] < 0.05,
        "explanation": r["explanation"],
    }


try:
    with st.spinner("Loading results..."):
        results, source = get_results()
    v = to_view(results)
except (OSError, ValueError) as exc:
    error_state(
        "Could not load the results.",
        f"Neither the API nor the local file worked. Details: {exc}",
    )
    st.stop()
except (KeyError, TypeError) as exc:
    error_state(
        "The results are not in the shape this page expects.",
        f"Missing or unexpected field: {exc}",
    )
    st.stop()

st.title("Earth System Trend Detective")

region_choices, variable_choices = get_choices(v["region"], v["variable"])
col_period, col_region, col_variable = st.columns(3)
col_period.selectbox("Period", [f"{v['start']} to {v['end']}"])
region = col_region.selectbox("Region", region_choices, key="region")
variable = col_variable.selectbox("Variable", variable_choices, key="variable")
is_default = region == v["region"] and variable == v["variable"]

# The default choice uses the results file. Any other choice asks the API.
chart_v = v
series_error = None
no_series = None
if not is_default:
    try:
        with st.spinner("Loading series..."):
            chart_v = {**v, **get_series(region, variable, v["units"])}
    except NoSeriesError as exc:
        no_series = exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        series_error = exc
failed = series_error is not None or no_series is not None

if failed:
    st.caption(f"{variable} in {region}")
else:
    st.caption(
        f"{chart_v['variable']} in {chart_v['region']}, "
        f"{chart_v['start']} to {chart_v['end']}"
    )
if not is_default:
    st.info(
        "The chart follows your selection. The cards, map and AI explanation "
        f"still describe {v['region']} ({v['variable']}) until results exist "
        "for other selections."
    )

slope_col, trend_col, p_col = st.columns(3)
arrow = {"increasing": "▲", "decreasing": "▼"}.get(v["trend"], "–")

with slope_col:
    units_note = v["units"]
    if not v["significant"]:
        units_note += " · not clearly different from zero"
    stat_card(
        "Slope (per month)",
        f"{v['slope']:+.4f}",
        units_note,
        muted=not v["significant"],
    )

with trend_col:
    stat_card(
        "Trend",
        f"{arrow} {v['trend'].capitalize()}",
        "Statistically significant"
        if v["significant"]
        else "No clear trend in this period",
    )

with p_col:
    stat_card(
        "p-value",
        f"{v['p']:.3f}",
        "Below 0.05, so significant"
        if v["significant"]
        else "Above 0.05, so not significant",
    )

chart_col, know_col = st.columns([2, 1])

with chart_col.container(border=True):
    can_anomaly = not failed and anomaly_available(
        chart_v["dates"], chart_v["values"]
    )
    title_col, toggle_col = st.columns([3, 2])
    mode = "raw"
    if can_anomaly:
        picked = toggle_col.radio(
            "View",
            ["Raw", "Anomaly"],
            horizontal=True,
            key="view_mode",
            label_visibility="collapsed",
        )
        mode = picked.lower()
    else:
        toggle_col.caption("Anomaly view needs at least two years of monthly data.")
    title_col.subheader(chart_title(mode))

    if series_error is not None:
        error_state(
            "Could not load this series.",
            f"The API did not return data for {region} / {variable}. "
            f"Details: {series_error}",
        )
    elif no_series is not None:
        empty_state("No data for this selection yet.", str(no_series))
    elif any(x is not None for x in chart_v["values"]):
        st.plotly_chart(make_chart(chart_v, mode), theme=None)
        if mode == "anomaly":
            st.caption(
                "Anomaly = value minus the average for the same calendar month "
                "over the whole period. Months seen once have no anomaly. "
                "No trend line here until the team confirms which series the "
                "slope is computed on."
            )
        elif chart_v["slope"] is None:
            st.caption(
                "No trend line: trend statistics for this selection "
                "are not available yet."
            )
    else:
        empty_state(
            "No data to chart for this selection.",
            "Try a different region or period.",
        )

with know_col.container(border=True):
    st.subheader("How we know")
    st.write("Data source: [dataset name]")
    st.write("Test: Mann-Kendall trend test")
    st.markdown(f"Kendall's tau: **{v['tau']:+.2f}**")
    st.caption("Tau runs from -1 to +1. It shows how consistently values rise or fall.")

with st.container(border=True):
    st.subheader("Trend map")
    points = mock_points()
    if points:
        st.plotly_chart(make_map(points, v["units"]), theme=None)
        st.caption(
            "Placeholder locations: the contract has no per-location trends yet, "
            "so these points are made up for layout only."
        )
    else:
        empty_state(
            "No locations to map yet.",
            "Per-location trends have not been provided.",
        )

with st.container(border=True):
    st.subheader("AI explanation")
    if (v["explanation"] or "").strip():
        st.write(v["explanation"])
    else:
        empty_state("No explanation yet.", "It appears once the AI step has run.")

footer = f"Showing results from: {source}"
if not is_default and not failed:
    footer += f" · series from API at {API_URL}"
st.caption(footer)