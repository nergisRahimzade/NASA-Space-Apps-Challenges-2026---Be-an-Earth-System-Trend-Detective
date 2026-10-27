import html

import streamlit as st


def stat_card(label, value, note="", muted=False):
    """A small card: label on top, big number or word, note underneath."""
    value_class = "esd-value esd-muted" if muted else "esd-value"
    st.markdown(
        '<div class="esd-card">'
        f'<div class="esd-label">{html.escape(label)}</div>'
        f'<div class="{value_class}">{html.escape(value)}</div>'
        f'<div class="esd-note">{html.escape(note)}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def empty_state(message, hint=""):
    """Shown when there is nothing to display (for example, an empty series)."""
    st.info(f"{message} {hint}".strip())


def error_state(title, detail):
    """Shown when something failed. Offers a retry button."""
    st.error(f"**{title}**\n\n{detail}")
    if st.button("Try again"):
        st.cache_data.clear()
        st.rerun()