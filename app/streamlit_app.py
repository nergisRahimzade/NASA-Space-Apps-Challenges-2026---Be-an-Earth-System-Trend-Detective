import streamlit as st
from charts import make_chart
from components import empty_state, error_state, stat_card
from maps import make_map
from mock_map import mock_points
from theme import apply_theme

from api_client import load_results

st.set_page_config(
    page_title="Earth System Trend Detective",
    page_icon="🛰️",
    layout="wide",
)
apply_theme()


@st.cache_data(ttl=60)
def get_results():
    return load_results()


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


# Loading and error states: show a spinner while fetching, and a friendly
# message (instead of a traceback) if the data can't be loaded or read.
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
st.caption(f"{v['variable']} in {v['region']}, {v['start']} to {v['end']}")

col_period, col_region, col_variable = st.columns(3)
col_period.selectbox("Period", [f"{v['start']} to {v['end']}"])
col_region.selectbox("Region", [v["region"]])
col_variable.selectbox("Variable", [v["variable"]])

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
    if v["values"]:
        st.plotly_chart(make_chart(v), theme=None)
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

st.caption(f"Showing data from: {source}")