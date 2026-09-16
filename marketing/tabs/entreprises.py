"""Entreprises — filtres NAF / tranche / recherche, métriques, export CSV.

Deux exports : la liste d'entreprises filtrée, et les contacts qualifiés
rattachés à ces mêmes entreprises (jointure sur `entities.attributes->>'siren'`).
L'export contacts est en deux temps (bouton « charger » puis download) pour ne
pas payer une requête Neon à chaque rerun de la page pendant le réglage des
filtres.
"""

from __future__ import annotations

import streamlit as st

from shared.filters import build_group

CONTACTS_STATE_KEY = "t_contacts_df"
CONTACTS_SIG_KEY = "t_contacts_sig"


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

    if df_t.empty:
        return

    sirens = sorted({
        s for s in df_t["siren"].dropna().astype(str).str.strip()
        if s.isdigit()
    })

    col_ent, col_ctc = st.columns(2)
    csv = df_t.to_csv(index=False).encode("utf-8")
    col_ent.download_button("⬇️ Export CSV entreprises", csv, "entreprises.csv", "text/csv",
                            use_container_width=True)
    load_clicked = col_ctc.button(
        f"👥 Charger les contacts de ces {len(sirens)} entreprises",
        key="t_load_contacts",
        disabled=not sirens,
        use_container_width=True,
        help="Contacts qualifiés rattachés aux entreprises affichées ci-dessus. "
             "Une requête au clic — pas à chaque changement de filtre.",
    )

    if target_total > len(df_t):
        st.caption(
            f"ℹ️ L'affichage est limité à {len(df_t)} entreprises sur {target_total} — "
            "l'export contacts ne couvre que les entreprises listées ci-dessus."
        )

    _render_contacts_block(cached_query, project_filter, sirens, load_clicked)


def _render_contacts_block(cached_query, project_filter: str, sirens: list[str],
                           load_clicked: bool) -> None:
    """Charge (au clic) et propose à l'export les contacts des SIREN affichés."""
    sig = (project_filter, tuple(sirens))

    if load_clicked:
        st.session_state[CONTACTS_STATE_KEY] = _fetch_contacts(
            cached_query, project_filter, sirens
        )
        st.session_state[CONTACTS_SIG_KEY] = sig

    # Filtres modifiés depuis le chargement → on jette le résultat périmé.
    if st.session_state.get(CONTACTS_SIG_KEY) != sig:
        st.session_state.pop(CONTACTS_STATE_KEY, None)
        st.session_state.pop(CONTACTS_SIG_KEY, None)
        return

    df_c = st.session_state.get(CONTACTS_STATE_KEY)
    if df_c is None:
        return

    st.divider()
    st.markdown("##### 👥 Contacts des entreprises filtrées")

    if df_c.empty:
        st.info("Aucun contact qualifié rattaché à ces entreprises.")
        return

    f1, f2 = st.columns(2)
    only_email = f1.checkbox("Email présent uniquement", value=False, key="t_ctc_email")
    only_cse = f2.checkbox("Élus CSE uniquement (cse_status=oui)", value=False, key="t_ctc_cse")
    st.caption(
        "Pool brut : tous les contacts rattachés, y compris `cse_status=inconnu` "
        "(issus d'une extraction large, qualité variable). Cocher « Élus CSE uniquement » "
        "pour ne garder que les mandats confirmés."
    )

    df_f = df_c
    if only_email:
        df_f = df_f[df_f["email"].notna()]
    if only_cse:
        df_f = df_f[df_f["cse_status"] == "oui"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Contacts", len(df_f))
    m2.metric("cse=oui", int((df_f["cse_status"] == "oui").sum()))
    m3.metric("avec email", int(df_f["email"].notna().sum()))
    m4.metric("avec téléphone", int(df_f["phone"].notna().sum()))

    st.dataframe(df_f, use_container_width=True, hide_index=True)

    st.download_button(
        f"⬇️ Export CSV contacts ({len(df_f)} lignes)",
        df_f.to_csv(index=False).encode("utf-8"),
        "contacts_entreprises.csv",
        "text/csv",
        type="primary",
        disabled=df_f.empty,
        key="t_ctc_dl",
    )


def _fetch_contacts(cached_query, project_filter: str, sirens: list[str]):
    """Contacts qualifiés des SIREN donnés. `sirens` est garanti numérique."""
    proj_clause = "" if project_filter == "Tous" else f" AND ql.project = '{project_filter}'"
    in_list = "','".join(sirens)
    return cached_query(f"""
        SELECT
            ql.first_name                                    AS prénom,
            ql.last_name                                     AS nom,
            ql.email,
            ql.phone,
            ql.role,
            ql.cse_status,
            ql.cse_level,
            ql.union_status,
            ql.union_name                                    AS syndicat,
            ql.union_mandate,
            e.attributes->>'employeur'                       AS entreprise,
            e.attributes->>'siren'                           AS siren,
            ql.source_date,
            jsonb_array_length(ql.evidences::jsonb)          AS nb_sources,
            (
                SELECT elem->>'source_url'
                FROM jsonb_array_elements(ql.evidences::jsonb) AS elem
                WHERE elem->>'source_url' IS NOT NULL
                LIMIT 1
            ) AS source_url
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE ql.status != 'merged'
          AND COALESCE(ql.meta->>'name_suspicious', 'false') <> 'true'
          AND e.attributes->>'siren' IN ('{in_list}')
          {proj_clause}
        ORDER BY entreprise, ql.cse_status = 'oui' DESC, nb_sources DESC
    """)
