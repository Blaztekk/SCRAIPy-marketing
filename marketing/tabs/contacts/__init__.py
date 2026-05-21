"""Contacts — orchestrates Explorer / Rdy mail / Rdy call sub-tabs."""

from __future__ import annotations

import streamlit as st

from marketing.tabs.contacts import explorer, rdy_call, rdy_mail


def render(scalar, cached_query, query, project_filter: str) -> None:
    sub_explorer, sub_mail, sub_call = st.tabs([
        "🔍 Explorer", "📧 Rdy mail", "📞 Rdy call",
    ])

    with sub_explorer:
        explorer.render(scalar, cached_query, query, project_filter)

    with sub_mail:
        rdy_mail.render(cached_query, project_filter)

    with sub_call:
        rdy_call.render(cached_query, project_filter)
