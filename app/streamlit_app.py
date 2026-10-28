import streamlit as st
from charts import make_chart

from api_client import load_results

st.set_page_config(
    page_title="Earth System Trend Detective",
    page_icon="🛰️",
    layout="wide",
)


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


results, source = get_results()
v = to_view(results)

st.title("Earth System Trend Detective")

col_period, col_region, col_variable = st.columns(3)
col_period.selectbox("Period", [f"{v['start']} to {v['end']}"])
col_region.selectbox("Region", [v["region"]])
col_variable.selectbox("Variable", [v["variable"]])

slope_col, trend_col, p_col = st.columns(3)

with slope_col.container(border=True):
    st.caption("Slope (per month)")
    st.subheader(f"{v['slope']:+.4f}")
    st.caption(v["units"])

with trend_col.container(border=True):
    st.caption("Trend")
    st.subheader(v["trend"].capitalize())
    st.caption("Significant" if v["significant"] else "Not significant")

with p_col.container(border=True):
    st.caption("p-value")
    st.subheader(f"{v['p']:.3f}")
    st.caption("Below 0.05" if v["significant"] else "Above 0.05")

chart_col, know_col = st.columns([2, 1])

with chart_col.container(border=True):
    st.plotly_chart(make_chart(v))

with know_col.container(border=True):
    st.subheader("How we know")
    st.write("Data source: [dataset name]")
    st.write("Test: Mann-Kendall trend test")
    st.write(f"Kendall's tau: {v['tau']:+.2f}")
    st.caption("Tau runs from -1 to +1. It shows how consistently values rise or fall.")

with st.container(border=True):
    st.subheader("Trend map")
    st.caption("Placeholder. The map arrives with its own ticket.")

with st.container(border=True):
    st.subheader("AI explanation")
    st.write(v["explanation"])

st.caption(f"Showing data from: {source}")