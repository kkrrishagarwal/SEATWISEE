"""Public portal — branded "DO! u want". Applicants register, rank programs and check their seat."""
from __future__ import annotations

import streamlit as st

from database import db_manager as db
from ui.common import BRAND, conn


def render() -> None:
    c = conn()
    st.markdown(f"<h1 style='margin-bottom:0'>{BRAND}</h1><p style='color:gray;margin-top:0'>Tell us what you want. Our solver finds the fairest seat for everyone.</p>", unsafe_allow_html=True)

    programs = db.load_programs(c)
    with st.expander("Browse programs", expanded=False):
        show = programs[["code", "name", "capacity", "min_score", "required_track"]].rename(
            columns={"code": "Code", "name": "Program", "capacity": "Seats", "min_score": "Min score", "required_track": "Track required"})
        show["Track required"] = show["Track required"].fillna("Any")
        st.dataframe(show, hide_index=True, width="stretch")

    col_reg, col_chk = st.columns([3, 2], gap="large")

    with col_reg:
        st.subheader("Register & rank your choices")
        with st.form("register", clear_on_submit=False):
            name = st.text_input("Full name")
            email = st.text_input("Email")
            score = st.slider("Entrance score", 0, 100, 70)
            track = st.selectbox("Your track", db.TRACKS)
            options = [f"{r.code} — {r.name}" for r in programs.itertuples()]
            ranked = st.multiselect("Rank up to 5 programs in order of preference (first = most wanted)", options, max_selections=5)
            submitted = st.form_submit_button("DO! I want these seats", type="primary")
        if submitted:
            if not name.strip() or "@" not in email or not ranked:
                st.error("Name, a valid email and at least one ranked program are required.")
            elif db.find_applicant_by_email(c, email):
                st.warning("That email is already registered. Use the lookup on the right.")
            else:
                code_to_id = dict(zip(programs.code, programs.id))
                ids = [code_to_id[o.split(" — ")[0]] for o in ranked]
                aid = db.add_applicant(c, name=name.strip(), email=email, score=score, track=track, ranked_program_ids=ids)
                st.success(f"Registered! Your applicant ID is **{aid}**. Seats are allocated by the admin in the next run.")
                eligible_warn = []
                for o, pid in zip(ranked, ids):
                    row = programs[programs.id == pid].iloc[0]
                    if score < row.min_score or (row.required_track and row.required_track != track):
                        eligible_warn.append(o.split(" — ")[0])
                if eligible_warn:
                    st.info("Heads-up: you currently don't meet the prerequisites for " + ", ".join(eligible_warn) + ". Those choices will be skipped by the solver.")

    with col_chk:
        st.subheader("Check my seat")
        q = st.text_input("Registered email", key="lookup_email", placeholder="applicant001@seatwisee.demo")
        if q:
            a = db.find_applicant_by_email(c, q)
            if not a:
                st.error("No applicant with that email.")
            else:
                st.write(f"**{a['name']}** · ID {a['id']} · {a['track']} · score {a['score']} · status *{a['status']}*")
                prefs = db.load_preferences(c)
                mine = prefs[prefs.applicant_id == a["id"]]
                st.caption("Your ranking: " + " › ".join(f"#{r.rank} {r.code}" for r in mine.itertuples()))
                seat = db.current_assignment_for(c, a["id"])
                if seat is None:
                    st.info("No allocation has been published yet.")
                elif seat["program_id"] is None:
                    st.warning("You are currently **unassigned**. You can raise an appeal with the admin office.")
                else:
                    st.success(f"You hold a seat in **{seat['code']} — {seat['program_name']}** (your choice #{seat['rank_obtained']}).")
                    if seat["previous_program_id"] and seat["previous_program_id"] != seat["program_id"]:
                        st.caption("This changed in the latest reallocation.")
