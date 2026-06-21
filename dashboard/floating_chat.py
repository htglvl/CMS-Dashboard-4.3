"""Floating chat widget for 'Ask the AI' feature using Streamlit chat components."""

import streamlit as st
from advanced_charts.recommendation_engine import RecommendationEngine


def render_floating_chat(risk_predictions, outages, charging_sites):
    """Render a floating chat widget using Streamlit's native chat components.

    Parameters
    ----------
    risk_predictions : pd.DataFrame
        Risk model predictions.
    outages : pd.DataFrame
        Historic outage data.
    charging_sites : pd.DataFrame
        Charging site locations.
    """
    # Initialize session state
    if "chat_open" not in st.session_state:
        st.session_state.chat_open = False
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []  # List of {"role": ..., "content": ...}

    # Custom CSS for floating button
    st.markdown("""
    <style>
    /* Floating chat toggle button */
    div[data-testid="stHorizontalBlock"] > div:last-child button {
        background: linear-gradient(135deg, #FF1493, #FF69B4) !important;
        color: white !important;
        border: none !important;
        border-radius: 50% !important;
        width: 56px !important;
        height: 56px !important;
        font-size: 24px !important;
        padding: 0 !important;
        box-shadow: 0 4px 15px rgba(255, 20, 147, 0.4) !important;
        position: fixed !important;
        bottom: 30px !important;
        right: 30px !important;
        z-index: 999999 !important;
    }
    div[data-testid="stHorizontalBlock"] > div:last-child button:hover {
        box-shadow: 0 6px 20px rgba(255, 20, 147, 0.6) !important;
        transform: scale(1.05);
    }

    /* Style the chat container when open */
    .chat-panel {
        position: fixed;
        bottom: 100px;
        right: 30px;
        width: 400px;
        max-height: 500px;
        background: white;
        border-radius: 16px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.2);
        z-index: 999998;
        overflow: hidden;
    }
    </style>
    """, unsafe_allow_html=True)

    # Toggle button at bottom-right
    col_spacer, col_btn = st.columns([20, 1])
    with col_btn:
        btn_label = "✕" if st.session_state.chat_open else "💬"
        if st.button(btn_label, key="chat_toggle_btn", help="Toggle AI Chat"):
            st.session_state.chat_open = not st.session_state.chat_open
            st.rerun()

    # Chat panel when open
    if st.session_state.chat_open:
        st.markdown("---")

        # Chat header
        st.markdown("### 🤖 Ask the AI")

        # Display existing messages using st.chat_message
        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # Chat input at the bottom
        if prompt := st.chat_input("Ask about risk, chargers, or community impact...", key="ai_chat_input"):
            # Add user message to history
            st.session_state.chat_messages.append({"role": "user", "content": prompt})

            # Display user message
            with st.chat_message("user"):
                st.markdown(prompt)

            # Get and display AI response with status indicator
            with st.chat_message("assistant"):
                with st.status("🤖 Thinking...", expanded=False) as status:
                    engine = RecommendationEngine(risk_predictions, outages, charging_sites)
                    response = engine.ask(prompt)
                    status.update(label="✅ Done!", state="complete", expanded=False)
                st.markdown(response)

            # Add assistant response to history
            st.session_state.chat_messages.append({"role": "assistant", "content": response})
            st.rerun()

        # Clear chat button
        if st.session_state.chat_messages:
            st.markdown("---")
            if st.button("🗑️ Clear Chat History", key="clear_chat_btn"):
                st.session_state.chat_messages = []
                st.rerun()
