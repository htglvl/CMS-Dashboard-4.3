"""Theme detection utilities."""

import streamlit as st


def detect_dark_mode() -> bool:
    """Detect whether the Streamlit app is running in dark mode."""
    try:
        return st.get_option("theme.base") == "dark"
    except Exception:
        return False
