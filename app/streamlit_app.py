import streamlit as st

from api_client import API_URL, load_choices, load_results, load_series
from charts import make_chart
from components import empty_state, error_state, stat_card
from maps import make_map
from mock_map import mock_points
from theme import apply_theme

st.set_page_config(
    page_title="Earth System Trend Detective",
    page_icon="🛰️",
    layout="wide",
)
apply_theme()

# Placeholder dropdown choices. The real list of regions is planned as an API
# endpoint (Day 12) and the variable is not decided yet, so these stand in.
EXTRA_REGIONS = ["Example Region B", "Example Region C"]
EXTRA_VARIABLES = ["Example variable B"]


@st.cache_data(ttl=60)
def get_results():
    return load_results()


@st.cache_data(ttl=60)
def get_series(region, variable):
    return load_series(region, variable)


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

col_period, col_region, col_variable = st.columns(3)
col_period.selectbox("Period", [f"{v['start']} to {v['end']}"])
region = col_region.selectbox("Region", [v["region"], *EXTRA_REGIONS], key="region")
variable = col_variable.selectbox(
    "Variable", [v["variable"], *EXTRA_VARIABLES], key="variable"
)
is_default = region == v["region"] and variable == v["variable"]

# The default choice uses the results file. Any other choice asks GET /series.
chart_v = v
series_error = None
if not is_default:
    try:
        with st.spinner("Loading series..."):
            data = get_series(region, variable)
        points = data["series"]
        period = data.get("period", {})
        chart_v = {
            **v,
            "region": data.get("region", region),
            "variable": data.get("variable", variable),
            "units": data.get("units", v["units"]),
            "start": period.get("start", v["start"]),
            "end": period.get("end", v["end"]),
            "dates": [pt["date"] for pt in points],
            "values": [pt["value"] for pt in points],
            # No trend statistics exist for this choice yet, so no trend line.
            "slope": None,
            "intercept": None,
        }
    except (OSError, ValueError, KeyError, TypeError) as exc:
        series_error = exc

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
    st.subheader("Line chart")
    if series_error is not None:
        error_state(
            "Could not load this series.",
            f"The API did not return data for {region} / {variable}. "
            f"Details: {series_error}",
        )
    elif any(x is not None for x in chart_v["values"]):
        st.plotly_chart(make_chart(chart_v), theme=None)
        if chart_v["slope"] is None:
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
if not is_default and series_error is None:
    footer += f" · series from API at {API_URL}"
st.caption(footer)