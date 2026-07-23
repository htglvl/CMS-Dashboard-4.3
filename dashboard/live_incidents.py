"""Live incidents panel rendering."""

import pandas as pd
import streamlit as st


def render_live_incidents(live_incidents, show_live_incidents, live_refresh_label):
    """Render the live incidents status panel.

    Parameters
    ----------
    live_incidents : pd.DataFrame
        Fetched live incidents data.
    show_live_incidents : bool
        Whether live incidents are enabled.
    live_refresh_label : str
        Current refresh interval label for the debug caption.
    """
    # Debug caption
    st.sidebar.caption(
        f"Live: enabled={show_live_incidents}, "
        f"refresh={live_refresh_label}, "
        f"rows={len(live_incidents)}"
    )

    if not show_live_incidents:
        return

    if live_incidents.empty:
        st.markdown(
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#28A745;margin-right:6px;"></span>'
            '**Live Incidents** — No active incidents',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:#DC3545;margin-right:6px;animation:pulse 1.5s infinite;"></span>'
            f'**Live Incidents** — {len(live_incidents)} active',
            unsafe_allow_html=True,
        )
        st.markdown(
            "<style>@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}</style>",
            unsafe_allow_html=True,
        )

        for _, inc in live_incidents.iterrows():
            inc_num = inc.get("incident_num", "N/A")
            status = inc.get("incident_status", "Unknown")
            customers_off = int(inc.get("customers_off_supply", 0) or 0)
            customers_aff = int(inc.get("customers_affected", 0) or 0)
            outage_time = inc.get("outage_time")
            est_restore = inc.get("estimated_restoration_time")

            outage_str = (
                outage_time.strftime("%d %b %Y, %H:%M")
                if pd.notna(outage_time) else "N/A"
            )
            restore_str = (
                est_restore.strftime("%d %b %Y, %H:%M")
                if pd.notna(est_restore) else "TBC"
            )

            with st.expander(f"🔴 {inc_num} — {inc.get('incident_type', 'Unknown')}", expanded=False):
                st.markdown(f"**Reported:** {outage_str}")
                st.markdown(f"**Customers Off Supply:** {customers_off:,}/{customers_aff:,}")
                st.markdown(f"**Status:** {status}")
                st.markdown(f"**Estimated Restoration:** {restore_str}")

    st.markdown("---")
