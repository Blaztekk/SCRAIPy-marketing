"""Rdy mail — leads avec email confirmé, triés par score composite.

Canonical location for the campaign-context expander : the widgets live here,
Rdy call reads via shared session_state keys.

Perf model : one stable SQL query per project (cached 120s by Streamlit).
Score, segment filter, also_phone filter and campaign bonuses are all applied
in pandas after the fetch — so changing them produces 0 Neon round-trip.
"""

from __future__ import annotations

import streamlit as st

from marketing.exports import render_export_block
from marketing.scoring import (
    build_score_popover_md,
    get_campaign_context,
    render_campaign_expander,
)
from marketing.scoring_pandas import compute_score

CHANNEL = "email"
DISPLAY_LIMIT = 1000


def render(cached_query, project_filter: str) -> None:
    render_campaign_expander(cached_query)

    hdr, info = st.columns([8, 1])
    hdr.caption("Leads avec email confirmé — triés par score composite")
    with info.popover("📊"):
        st.markdown(build_score_popover_md())

    seg = st.radio(
        "Filtre", ["Tous", "CSE uniquement", "Syndiqué uniquement"],
        horizontal=True, key="rm_seg",
    )
    also_phone = st.checkbox(
        "Possède aussi un téléphone", value=False, key="rm_also_phone"
    )

    df = _fetch_pool(cached_query, project_filter)
    df = _apply_filters(df, seg=seg, also_phone=also_phone)
    df = _score_and_sort(df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Leads prêts (email)", len(df))
    if not df.empty:
        m2.metric("CSE=oui",     int((df["cse_status"] == "oui").sum()))
        m3.metric("Aussi tél.",  int(df["phone"].notna().sum()))
        m4.metric("Score moyen", round(float(df["score"].mean()), 1))

    st.dataframe(
        df.drop(columns=["_lead_id"]).head(DISPLAY_LIMIT),
        use_container_width=True,
        hide_index=True,
    )

    if not df.empty:
        render_export_block(df.head(DISPLAY_LIMIT), channel=CHANNEL, key_prefix="rm")


def _fetch_pool(cached_query, project_filter: str):
    """One stable SQL : email IS NOT NULL + project. No score, no seg, no also."""
    proj_clause = "" if project_filter == "Tous" else f" AND ql.project = '{project_filter}'"
    return cached_query(f"""
        SELECT
            ql.id                                        AS _lead_id,
            ql.first_name                                AS prénom,
            ql.last_name                                 AS nom,
            ql.email,
            ql.phone,
            ql.role,
            ql.cse_status,
            ql.union_status,
            ql.union_name                                AS syndicat,
            e.attributes->>'employeur'                   AS entreprise,
            e.attributes->>'siren'                       AS siren,
            jsonb_array_length(ql.evidences::jsonb)      AS nb_sources,
            ql.source_date
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE ql.status != 'merged'
          AND ql.email IS NOT NULL
          {proj_clause}
    """)


def _apply_filters(df, *, seg: str, also_phone: bool):
    if df.empty:
        return df
    if seg == "CSE uniquement":
        df = df[df["cse_status"] == "oui"]
    elif seg == "Syndiqué uniquement":
        df = df[df["union_status"] == "oui"]
    if also_phone:
        df = df[df["phone"].notna()]
    return df


def _score_and_sort(df):
    if df.empty:
        df = df.copy()
        df["score"] = []
        return df
    cu, cc = get_campaign_context()
    df = df.copy()
    df["score"] = compute_score(df, camp_union=cu, camp_company=cc)
    return df.sort_values(
        ["score", "nb_sources"], ascending=[False, False]
    ).reset_index(drop=True)
