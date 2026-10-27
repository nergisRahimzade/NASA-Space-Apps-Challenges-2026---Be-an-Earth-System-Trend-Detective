"""The look of the app, in one place: colors, fonts, and shared styling.

Streamlit's own base theme lives in .streamlit/config.toml. If you change the
background, panel, text or accent color here, change it there too.
"""

import streamlit as st

# Colors (from docs/design_notes.md)
BACKGROUND = "#0E1420"
PANEL = "#161E2E"
BORDER = "#2A3447"
TEXT = "#E6E9EF"
MUTED = "#8A94A6"
ACCENT = "#F2B84B"

# Blue and red are reserved for cooling and warming on the map.
COOLING = "#3B82C4"
WARMING = "#E4572E"
NEUTRAL = "#D9DEE7"
MAP_LAND = "#1C2639"
MAP_LINES = "#3A4A63"

# Fonts: system fonts, so nothing has to be downloaded.
FONT_HEADING = 'Georgia, "Times New Roman", serif'
FONT_BODY = '-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
FONT_NUMBERS = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

# Doubled braces {{ }} are how a CSS block is written inside an f-string.
CSS = f"""
<style>
h1, h2, h3 {{
    font-family: {FONT_HEADING} !important;
    letter-spacing: 0.01em;
}}
h1 {{
    color: {ACCENT} !important;
}}
.block-container {{
    padding-top: 2rem;
}}
div[data-testid="stVerticalBlockBorderWrapper"][data-border="true"] {{
    background-color: {PANEL};
    border-color: {BORDER} !important;
    border-radius: 10px !important;
}}
.esd-card {{
    background-color: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 14px 16px;
    min-height: 112px;
}}
.esd-label {{
    color: {MUTED};
    font-size: 0.85rem;
}}
.esd-value {{
    color: {TEXT};
    font-family: {FONT_NUMBERS};
    font-size: 1.7rem;
    font-weight: 600;
    margin: 4px 0;
}}
.esd-value.esd-muted {{
    color: {MUTED};
}}
.esd-note {{
    color: {MUTED};
    font-size: 0.8rem;
}}
</style>
"""


def apply_theme():
    """Inject the shared styling. Call once, right after st.set_page_config()."""
    st.markdown(CSS, unsafe_allow_html=True)


def style_figure(fig, height):
    """Give a Plotly figure the app's colors and fonts."""
    fig.update_layout(
        height=height,
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": FONT_BODY, "color": TEXT},
        hoverlabel={
            "bgcolor": PANEL,
            "bordercolor": BORDER,
            "font": {"color": TEXT},
        },
    )
    return fig