"""Explorer — filtres avancés multi-critères + inspecteur contact."""

from __future__ import annotations

import html as _html
import re as _re

import streamlit as st

from shared.filters import build_group


def render(scalar, cached_query, query, project_filter: str) -> None:
    # Groupe 1 : Statuts
    with st.container(border=True):
        hc, mc, pc = st.columns([4, 1, 1])
        hc.markdown("##### Groupe 1 — Statuts CSE / Syndicat")
        g1_mode = mc.radio("Mode G1", ["ET", "OU"], horizontal=True, key="ql_g1_mode",
                           label_visibility="collapsed")
        with pc.popover("ℹ️"):
            st.markdown("""
**Mode ET** : tous les critères du groupe doivent correspondre.
**Mode OU** : au moins un suffit.

**Exemples :**
- `cse=oui` + `union=oui` en **OU** → élus CSE *ou* syndiqués (les deux)
- `cse=oui` + `Instance=CSEC` en **ET** → élus au CSE central uniquement
""")
        c1, c2, c3, c4 = st.columns(4)
        cse_f = c1.selectbox("cse_status", ["Tous", "oui", "non", "inconnu"], key="ql_cse",
                             help="oui = élu·e confirmé·e au CSE\nnon = pas élu·e\ninconnu = statut non confirmé dans la source")
        union_f = c2.selectbox("union_status", ["Tous", "oui", "non", "inconnu"], key="ql_union",
                               help="oui = syndiqué·e confirmé·e\nnon = non syndiqué·e\ninconnu = non confirmé dans la source")
        cse_level_f = c3.selectbox("Instance CSE", ["Tous", "CSE", "CSEC", "(vide)"], key="ql_lvl",
                                   help="CSE = comité d'établissement\nCSEC = CSE central (niveau groupe)")
        union_name_opts = ["Tous", "(vide)"] + cached_query(
            "SELECT DISTINCT union_name FROM qualified_leads WHERE union_name IS NOT NULL ORDER BY union_name"
        )["union_name"].tolist()
        union_name_f = c4.selectbox("Syndicat", union_name_opts, key="ql_un",
                                    help="Filtrer par organisation syndicale (CFDT, CGT, FO, CFE-CGC…)")

    _sp1, ic, _sp2, ipc = st.columns([2, 2, 1, 1])
    inter_mode = ic.radio("Combiner les groupes avec :", ["ET", "OU"], horizontal=True, key="ql_inter")
    with ipc.popover("ℹ️"):
        st.markdown("""
**ET** : les deux groupes doivent être satisfaits simultanément.
**OU** : satisfaire l'un *ou* l'autre suffit.

**Exemples concrets :**

| Objectif | G1 | inter | G2 |
|---|---|---|---|
| Élus CSE joignables | cse=oui | **ET** | email ✓ |
| Quelqu'un qu'on peut contacter, peu importe le statut | *(vide)* | — | email OU phone |
| Élus CSE ou syndiqués avec coordonnées | cse OU union | **ET** | email OU phone |
""")

    # Groupe 2 : Coordonnées
    with st.container(border=True):
        hc2, mc2, pc2 = st.columns([4, 1, 1])
        hc2.markdown("##### Groupe 2 — Coordonnées")
        g2_mode = mc2.radio("Mode G2", ["ET", "OU"], index=1, horizontal=True, key="ql_g2_mode",
                            label_visibility="collapsed")
        with pc2.popover("ℹ️"):
            st.markdown("""
**Mode ET** : doit avoir *tous* les éléments cochés.
**Mode OU** : avoir *au moins un* suffit.

- Email **ET** phone → contacts joignables par les deux canaux
- Email **OU** phone → contacts joignables par au moins un canal
""")
        c1, c2, c3 = st.columns(3)
        has_email = c1.checkbox("email présent", value=True, key="ql_he",
                                help="N'afficher que les contacts avec une adresse email connue")
        has_phone = c2.checkbox("phone présent", value=True, key="ql_hp",
                                help="N'afficher que les contacts avec un numéro de téléphone connu")
        has_name = c3.checkbox("nom présent", value=True, key="ql_hn",
                               help="N'afficher que les contacts dont le prénom ou nom est renseigné")

    st.markdown("**Contexte** *(toujours ET, indépendamment des groupes)*")
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    siren_f = r2c1.text_input("SIREN entreprise", key="ql_siren",
                              help="SIREN à 9 chiffres — restreint les résultats à une seule entreprise")
    name_search = r2c2.text_input("Nom / email contient", key="ql_name",
                                  help="Recherche libre sur prénom, nom de famille, email ou raison sociale")
    min_ev = r2c3.number_input("Min sources", min_value=0, max_value=20, value=0, step=1, key="ql_minev",
                               help="Nombre minimum de sources ayant identifié ce contact. Plus élevé = plus fiable. Recommandé : 2+")
    source_max_years = r2c4.number_input("Source < X ans (0=off)", min_value=0, max_value=20, value=0, step=1, key="ql_freshness",
                                         help="Exclure les contacts dont toutes les sources datent de plus de X ans. 0 = pas de filtre de date.")
    limit_ql = st.number_input("Limite résultats", min_value=50, max_value=5000, value=500, step=50, key="ql_lim",
                               help="Nombre max de lignes affichées. Si 'Total filtres' > cette valeur, augmenter ici avant d'exporter.")

    where: list[str] = ["ql.status != 'merged'"]
    if project_filter != "Tous":
        where.append(f"ql.project = '{project_filter}'")

    g1: list[str] = []
    if cse_f != "Tous":
        g1.append(f"ql.cse_status = '{cse_f}'")
    if union_f != "Tous":
        g1.append(f"ql.union_status = '{union_f}'")
    if cse_level_f == "(vide)":
        g1.append("ql.cse_level IS NULL")
    elif cse_level_f != "Tous":
        g1.append(f"ql.cse_level = '{cse_level_f}'")
    if union_name_f == "(vide)":
        g1.append("ql.union_name IS NULL")
    elif union_name_f != "Tous":
        safe = union_name_f.replace("'", "''")
        g1.append(f"ql.union_name = '{safe}'")

    g2: list[str] = []
    if has_email:
        g2.append("ql.email IS NOT NULL")
    if has_phone:
        g2.append("ql.phone IS NOT NULL")
    if has_name:
        g2.append("(ql.first_name IS NOT NULL OR ql.last_name IS NOT NULL)")

    active_groups = [g for g in [build_group(g1, g1_mode), build_group(g2, g2_mode)] if g]
    if active_groups:
        inter_op = " AND " if inter_mode == "ET" else " OR "
        where.append("(" + inter_op.join(active_groups) + ")")

    if siren_f:
        safe = siren_f.strip().replace("'", "''")
        where.append(f"e.attributes->>'siren' = '{safe}'")
    if name_search:
        safe = name_search.replace("'", "''")
        where.append(
            f"(ql.first_name ILIKE '%{safe}%' OR ql.last_name ILIKE '%{safe}%' "
            f"OR ql.email ILIKE '%{safe}%' OR e.canonical_label ILIKE '%{safe}%')"
        )
    if min_ev > 0:
        where.append(f"jsonb_array_length(ql.evidences::jsonb) >= {int(min_ev)}")
    if source_max_years > 0:
        where.append(f"ql.source_date >= NOW() - INTERVAL '{int(source_max_years)} years'")

    where_sql = " AND ".join(where)

    df_ql = cached_query(f"""
        SELECT
            ql.id,
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
            ql.company,
            e.attributes->>'employeur'                       AS entreprise,
            e.attributes->>'siren'                           AS siren,
            ql.source_date,
            jsonb_array_length(ql.evidences::jsonb)          AS nb_sources,
            (
                SELECT elem->>'source_url'
                FROM jsonb_array_elements(ql.evidences::jsonb) AS elem
                WHERE elem->>'source_url' IS NOT NULL
                LIMIT 1
            ) AS source_url,
            (
                SELECT string_agg(elem->>'source_url', E'\n')
                FROM jsonb_array_elements(ql.evidences::jsonb) AS elem
                WHERE elem->>'source_url' IS NOT NULL
            ) AS toutes_sources,
            ROUND(ql.confidence::numeric, 2)                 AS confiance
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE {where_sql}
        ORDER BY ql.cse_status='oui' DESC, nb_sources DESC, ql.collected_at DESC
        LIMIT {int(limit_ql)}
    """)

    total_count = scalar(f"""
        SELECT COUNT(*) FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE {where_sql}
    """)

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total (filtres)", total_count,
              delta=f"affichage limité à {len(df_ql)}" if total_count > len(df_ql) else None,
              delta_color="off")
    if not df_ql.empty:
        m2.metric("cse=oui",       int((df_ql["cse_status"] == "oui").sum()))
        m3.metric("union=oui",     int((df_ql["union_status"] == "oui").sum()))
        m4.metric("avec email",    int(df_ql["email"].notna().sum()))
        m5.metric("avec téléphone", int(df_ql["phone"].notna().sum()))

    display_df = df_ql.drop(columns=["id"], errors="ignore")
    event = st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "source_url": st.column_config.LinkColumn(
                "source (lien)",
                display_text=r"https?://(?:www\.)?([^/]+).*",
                width="medium",
            ),
            "toutes_sources": st.column_config.TextColumn(
                "toutes les sources",
                help="Toutes les URLs sources (une par ligne). Cliquer la ligne pour voir les détails.",
                width="large",
            ),
        },
    )

    # ── Inspecteur contact ────────────────────────────────────────────────────
    sel_id = ""
    if event.selection and event.selection.rows:
        sel_id = str(df_ql.iloc[event.selection.rows[0]]["id"])

    st.divider()
    cap_col, pop_col = st.columns([7, 1])
    if not sel_id:
        cap_col.caption("👆 Clique une ligne pour voir les détails et les sources du contact")
    with pop_col.popover("ℹ️"):
        st.markdown("""
**L'inspecteur affiche :**
- Coordonnées complètes (email, téléphone, statut CSE/syndicat, mandat)
- Entreprise avec niveau de confiance
- Chaque source ayant permis d'identifier ce contact

**Dans chaque source**, un extrait du document original est affiché avec le **nom surligné en jaune** — pour vérifier le contexte (page web, PDF de résultats électoraux, liste syndicale…).

> Le champ `nb_sources` dans le tableau = nombre de sources distinctes. Un contact avec 3+ sources est très probablement correct.
""")
    if not sel_id:
        return

    full = cached_query(
        """
        SELECT ql.first_name, ql.last_name, ql.email, ql.phone, ql.role,
               ql.cse_status, ql.cse_level, ql.union_status, ql.union_name,
               ql.union_mandate, ql.company, ql.company_confidence,
               ql.source_date, ql.confidence, ql.evidences, ql.meta,
               e.canonical_label, e.attributes
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE ql.id = :id
        """,
        {"id": sel_id},
    )
    if full.empty:
        return

    row = full.iloc[0]
    st.markdown(
        f"### {row['first_name'] or ''} {row['last_name'] or ''}"
        f" — {row['role'] or '(rôle inconnu)'}"
    )
    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Coordonnées**")
        st.write({
            "email":        row["email"],
            "phone":        row["phone"],
            "cse_status":   row["cse_status"],
            "cse_level":    row["cse_level"],
            "union_status": row["union_status"],
            "syndicat":     row["union_name"],
            "mandat":       row["union_mandate"],
        })
    with cB:
        st.markdown("**Entreprise**")
        st.write({
            "nom":              row["canonical_label"],
            "siren":            (row["attributes"] or {}).get("siren"),
            "company_confiance": row["company_confidence"],
            "source_date":      str(row["source_date"]),
            "confiance":        row["confidence"],
        })

    st.markdown(f"**Sources ({len(row['evidences'] or [])})**")
    for i, ev in enumerate(row["evidences"] or [], 1):
        with st.expander(
            f"#{i} — {ev.get('extracting_module', '?')} "
            f"— conf {ev.get('confidence', '?')}"
        ):
            url = ev.get("source_url")
            if url:
                st.markdown(f"**URL** : [{url}]({url})")
            else:
                st.markdown("**URL** : *(aucune)*")
            st.markdown(
                f"**Date source** : {ev.get('source_date') or '?'}"
                f" · **Collecté le** : {ev.get('collected_at') or '?'}"
            )
            if ev.get("snippet"):
                st.code(ev["snippet"])

            if not url:
                continue

            doc_df = query(
                """
                SELECT parsed_text, meta->>'title' AS title,
                       content_type, meta->>'source_date' AS source_date
                FROM captured_documents
                WHERE url = :url
                ORDER BY collected_at DESC LIMIT 1
                """,
                url=url,
            )
            if doc_df.empty:
                continue

            doc = doc_df.iloc[0]
            parsed = doc["parsed_text"] or ""
            st.caption(
                f"📄 **{doc['title'] or ''}** · {doc['content_type']}"
                f" · source_date: {doc['source_date']} · {len(parsed):,} chars"
            )
            if not parsed:
                continue

            search_term = (row["last_name"] or row["first_name"] or "").strip()
            pos = parsed.lower().find(search_term.lower()) if search_term else -1
            if pos >= 0:
                start, end = max(0, pos - 1500), min(len(parsed), pos + 1500)
                excerpt = parsed[start:end]
                label = "Texte capturé (contexte autour du nom)"
            else:
                excerpt = parsed[:3000]
                label = "Texte capturé (début)"

            exc_esc = _html.escape(excerpt)
            for term in [row["last_name"], row["first_name"]]:
                if term and len(term.strip()) > 1:
                    pat = _re.compile(
                        _re.escape(_html.escape(term.strip())),
                        _re.IGNORECASE,
                    )
                    exc_esc = pat.sub(
                        lambda m: (
                            f'<mark style="background:#ffd700;'
                            f'color:#111;font-weight:bold">'
                            f'{m.group(0)}</mark>'
                        ),
                        exc_esc,
                    )
            st.caption(label)
            st.markdown(
                f'<div style="height:380px;overflow-y:auto;'
                f'font-family:monospace;font-size:12px;padding:12px;'
                f'border:1px solid #444;border-radius:4px;'
                f'white-space:pre-wrap;line-height:1.6">'
                f'{exc_esc.replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )
