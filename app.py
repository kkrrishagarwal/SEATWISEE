"""SEATWISEE — Streamlit entry point. Public UI brand: "DO! u want"."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))

st.set_page_config(page_title="DO! u want · SEATWISEE", page_icon="🎯", layout="wide")

public = importlib.import_module("ui.1_public_portal")
admin = importlib.import_module("ui.2_admin_dashboard")
appeals = importlib.import_module("ui.3_appeal_studio")

with st.sidebar:
    st.markdown("### SEATWISEE")
    st.caption("Constraint-based seat allocation · Google OR-Tools CP-SAT · SQLite · Streamlit")
    st.markdown(
        "- **Mode A** maximises preference points\n"
        "- **Mode B** adds a displacement penalty μ so existing seats are protected\n"
        "- **Appeals** force one request and report the ripple\n"
        "- An **independent validator** re-checks every rule"
    )

tab1, tab2, tab3 = st.tabs(["🎯 DO! u want — Public portal", "🛠 Admin dashboard", "⚖️ Appeal studio"])
with tab1:
    public.render()
with tab2:
    admin.render()
with tab3:
    appeals.render()
