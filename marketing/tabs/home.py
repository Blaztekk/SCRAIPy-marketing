"""Accueil — metrics + top-20 entreprises CSE."""

from __future__ import annotations

import streamlit as st


def render(scalar, cached_query, proj_clause: str, ql_proj_clause: str) -> None:
    st.subheader("Vue d'ensemble")

    live = f"status != 'merged'{proj_clause}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏢 Entreprises confirmées", scalar(f"SELECT COUNT(*) FROM targets WHERE status='confirmed'{proj_clause}"))
    c2.metric("🟢 Élus CSE",              scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND cse_status='oui'"))
    c3.metric("📧 Avec email",            scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND email IS NOT NULL"))
    c4.metric("📞 Avec téléphone",        scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND phone IS NOT NULL"))

    st.divider()
    st.subheader("Contacts qualifiés")

    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Élus CSE (oui)",  scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND cse_status='oui'"))
    m2.metric("🔵 Syndiqués (oui)",  scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND union_status='oui'"))
    m3.metric("⚪ Statut inconnu",   scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {live} AND cse_status='inconnu'"))

    st.divider()
    st.subheader("Élus CSE par entreprise (top 20)")
    df_per_siren = cached_query(f"""
        SELECT
            COALESCE(e.attributes->>'employeur', 'INCONNU') AS entreprise,
            e.attributes->>'siren'                          AS siren,
            COUNT(DISTINCT ql.entity_id)                    AS contacts_uniques,
            COUNT(*)                                        AS leads_total,
            ROUND(AVG(jsonb_array_length(ql.evidences::jsonb))::numeric, 2) AS avg_sources
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE ql.status != 'merged' AND ql.cse_status='oui'{ql_proj_clause}
        GROUP BY 1, 2
        ORDER BY contacts_uniques DESC
        LIMIT 20
    """)
    st.dataframe(df_per_siren, use_container_width=True, hide_index=True)
