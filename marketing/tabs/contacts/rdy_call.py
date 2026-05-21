"""Rdy call — leads avec téléphone confirmé.

Reads campaign context from session_state (widgets live in rdy_mail).
"""

from __future__ import annotations

import streamlit as st

from marketing.scoring import (
    build_score_popover_md,
    build_score_sql,
    render_campaign_indicator,
)


def render(cached_query, project_filter: str) -> None:
    render_campaign_indicator()

    hdr, info = st.columns([8, 1])
    hdr.caption("Leads avec téléphone confirmé — triés par score composite")
    with info.popover("📊"):
        st.markdown(build_score_popover_md())

    seg = st.radio(
        "Filtre", ["Tous", "CSE uniquement", "Syndiqué uniquement"],
        horizontal=True, key="rc_seg",
    )

    where = ["ql.status != 'merged'", "ql.phone IS NOT NULL"]
    if project_filter != "Tous":
        where.append(f"ql.project = '{project_filter}'")
    if seg == "CSE uniquement":
        where.append("ql.cse_status = 'oui'")
    elif seg == "Syndiqué uniquement":
        where.append("ql.union_status = 'oui'")

    where_sql = " AND ".join(where)
    score_sql = build_score_sql()

    df = cached_query(f"""
        SELECT
            ({score_sql})                                AS score,
            ql.first_name                                AS prénom,
            ql.last_name                                 AS nom,
            ql.phone,
            ql.email,
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
    m1.metric("Leads prêts (tél.)", len(df))
    if not df.empty:
        m2.metric("CSE=oui",     int((df["cse_status"] == "oui").sum()))
        m3.metric("Aussi email", int(df["email"].notna().sum()))
        m4.metric("Score moyen", round(float(df["score"].mean()), 1))

    st.dataframe(df, use_container_width=True, hide_index=True)

    if not df.empty:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export CSV — Rdy call", csv, "rdy_call.csv", "text/csv",
                           type="primary")
