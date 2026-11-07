import html

import streamlit as st
from theme import (
    BADGE_GREEN_BG,
    BADGE_GREEN_BORDER,
    BADGE_GREEN_TEXT,
    BADGE_GREY_BG,
    BADGE_GREY_BORDER,
    BADGE_GREY_TEXT,
)

SIGNIFICANCE_LEVEL = 0.05


def is_significant(p, trend_label=None):
    """True or False, or None when there is no p-value to judge.

    The trend test already says "no trend" when p is not below its cut-off,
    so that label also counts as not significant.
    """
    if p is None:
        return None
    if trend_label == "no trend":
        return False
    return p < SIGNIFICANCE_LEVEL


def format_signed(value, digits):
    """+0.0420 style number, or n/a when the value is missing.

    A tiny non-zero value would show as +0.0000, so with 3 or more decimals
    it switches to scientific notation (+4.2e-05) instead.
    """
    if value is None:
        return "n/a"
    if digits >= 3 and value != 0 and abs(value) < 0.5 * 10 ** (-digits):
        return f"{value:+.1e}"
    return f"{value:+.{digits}f}"

def format_p(p):
    """p-value with 3 decimals, <0.001 for tiny values, n/a when missing."""
    if p is None:
        return "n/a"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _badge(significant):
    if significant:
        text = "✓ Significant"
        bg, fg, border = BADGE_GREEN_BG, BADGE_GREEN_TEXT, BADGE_GREEN_BORDER
    else:
        text = "– Not significant"
        bg, fg, border = BADGE_GREY_BG, BADGE_GREY_TEXT, BADGE_GREY_BORDER
    return (
        '<span style="display:inline-block;padding:2px 10px;border-radius:999px;'
        f"font-size:0.78rem;font-weight:600;background:{bg};color:{fg};"
        f'border:1px solid {border};">{text}</span>'
    )


def stat_card(label, value, note="", muted=False, significant=None):
    """A small card: label, big value, note, and an optional significance badge.

    significant: True gives a green badge, False a grey one, None no badge.
    """
    value_class = "esd-value esd-muted" if muted else "esd-value"
    badge = ""
    if significant is not None:
        badge = f'<div style="margin-top:8px;">{_badge(significant)}</div>'
    st.markdown(
        '<div class="esd-card">'
        f'<div class="esd-label">{html.escape(label)}</div>'
        f'<div class="{value_class}">{html.escape(value)}</div>'
        f'<div class="esd-note">{html.escape(note)}</div>'
        f"{badge}"
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