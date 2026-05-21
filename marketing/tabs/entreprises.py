"""Entreprises — filtres NAF / tranche / recherche, métriques, export CSV."""

from __future__ import annotations

import streamlit as st

from shared.filters import build_group


def render(scalar, cached_query, project_filter: str) -> None:
    t_mode = st.radio("Mode filtres", ["ET", "OU"], horizontal=True, key="t_mode",
                      help="ET = tous les critères requis. OU = au moins un suffit.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        t_status_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT status FROM targets ORDER BY status"
        )["status"].tolist()
        target_status = st.selectbox("Statut", t_status_opts, key="t_status",
                                     help="confirmed = entreprise validée dans le périmètre\nto_confirm = en attente de validation\nrejected = hors périmètre")
    with col2:
        naf_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT naf_code FROM targets WHERE naf_code IS NOT NULL ORDER BY naf_code"
        )["naf_code"].tolist()
        target_naf = st.selectbox("Code NAF", naf_opts, key="t_naf",
                                  help="Code d'activité INSEE (ex: 35.11Z = production d'électricité, 64.19Z = banques)")
    with col3:
        bracket_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT headcount_bracket FROM targets WHERE headcount_bracket IS NOT NULL ORDER BY headcount_bracket"
        )["headcount_bracket"].tolist()
        target_bracket = st.selectbox("Tranche effectif", bracket_opts, key="t_bracket",
                                      help="Tranche INSEE d'effectif salarié (ex: 5001_10000 = entre 5 000 et 10 000 salariés)")
    with col4:
        target_search = st.text_input("Recherche nom / SIREN", placeholder="ex: EDF, 552081317…",
                                      help="Recherche par nom d'entreprise (partiel) ou SIREN exact à 9 chiffres")

    t_fixed = ["1=1"]
    t_dynamic: list[str] = []
    if project_filter != "Tous":
        t_fixed.append(f"project = '{project_filter}'")
    if target_status != "Tous":
        t_dynamic.append(f"status = '{target_status}'")
    if target_naf != "Tous":
        t_dynamic.append(f"naf_code = '{target_naf}'")
    if target_bracket != "Tous":
        t_dynamic.append(f"headcount_bracket = '{target_bracket}'")
    if target_search:
        safe = target_search.replace("'", "''")
        t_dynamic.append(f"(label ILIKE '%{safe}%' OR siren = '{safe}')")
    t_groups = [g for g in [build_group(t_dynamic, t_mode)] if g] if t_dynamic else []
    t_where_sql = " AND ".join(t_fixed + (t_groups or []))

    target_total = scalar(f"SELECT COUNT(*) FROM targets WHERE {t_where_sql}")

    df_t = cached_query(f"""
        SELECT
            label          AS entreprise,
            siren,
            naf_code,
            headcount_bracket AS tranche_effectif,
            status         AS statut,
            ROUND(confidence::numeric, 2) AS confiance,
            address        AS adresse
        FROM targets
        WHERE {t_where_sql}
        ORDER BY confidence DESC, label
        LIMIT 1000
    """)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total (filtres)", target_total,
              delta=f"affichage limité à {len(df_t)}" if target_total > len(df_t) else None,
              delta_color="off")
    if not df_t.empty:
        c2.metric("✅ Confirmées", int((df_t["statut"] == "confirmed").sum()))
        c3.metric("⏳ En attente", int((df_t["statut"] == "to_confirm").sum()))

    st.dataframe(df_t, use_container_width=True, hide_index=True)

    if not df_t.empty:
        csv = df_t.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export CSV entreprises", csv, "entreprises.csv", "text/csv")
