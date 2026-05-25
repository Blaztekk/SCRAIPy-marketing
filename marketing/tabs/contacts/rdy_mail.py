"""Rdy mail — leads avec email confirmé, triés par score composite.

Canonical location for the campaign-context expander : the widgets live here,
Rdy call reads via shared session_state keys.
"""

from __future__ import annotations

import streamlit as st

from marketing.exports import render_export_block
from marketing.scoring import (
    build_score_popover_md,
    build_score_sql,
    render_campaign_expander,
)

CHANNEL = "email"


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

    where = ["ql.status != 'merged'", "ql.email IS NOT NULL"]
    if project_filter != "Tous":
        where.append(f"ql.project = '{project_filter}'")
    if seg == "CSE uniquement":
        where.append("ql.cse_status = 'oui'")
    elif seg == "Syndiqué uniquement":
        where.append("ql.union_status = 'oui'")
    if also_phone:
        where.append("ql.phone IS NOT NULL")

    where_sql = " AND ".join(where)
    score_sql = build_score_sql()

    df = cached_query(f"""
        SELECT
            ql.id                                        AS _lead_id,
            ({score_sql})                                AS score,
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
        WHERE {where_sql}
        ORDER BY score DESC, nb_sources DESC
        LIMIT 1000
    """)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Leads prêts (email)", len(df))
    if not df.empty:
        m2.metric("CSE=oui",     int((df["cse_status"] == "oui").sum()))
        m3.metric("Aussi tél.",  int(df["phone"].notna().sum()))
        m4.metric("Score moyen", round(float(df["score"].mean()), 1))

    st.dataframe(
        df.drop(columns=["_lead_id"]),
        use_container_width=True,
        hide_index=True,
    )

    if not df.empty:
        render_export_block(df, channel=CHANNEL, key_prefix="rm")
