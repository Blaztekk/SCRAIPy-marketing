"""SCRAIPy — Marketing Explorer (read-only).

Ce fichier est le dashboard public pour l'équipe marketing.
Il vit dans DEUX endroits :
  - d:\\Projets\\SCRAIPy\\dashboard_marketing.py        ← source de travail (modifier ici)
  - d:\\Projets\\SCRAIPy-marketing\\dashboard_marketing.py ← repo public déployé sur Streamlit Cloud

══ WORKFLOW DE MISE À JOUR ══════════════════════════════════════

1. Modifier ce fichier dans SCRAIPy (source de vérité)
2. Copier vers le repo marketing :
       copy "d:\\Projets\\SCRAIPy\\dashboard_marketing.py" "d:\\Projets\\SCRAIPy-marketing\\dashboard_marketing.py"
3. Commiter + pusher le repo marketing :
       cd d:\\Projets\\SCRAIPy-marketing
       git add dashboard_marketing.py
       git commit -m "update: dashboard marketing"
       git push
4. Streamlit Cloud redéploie automatiquement (~1 min).

══ DÉPLOIEMENT STREAMLIT CLOUD ════════════════════════════════

Repo public  : https://github.com/Blaztekk/SCRAIPy-marketing
App settings > Secrets :
    [secrets]
    DATABASE_URL = "postgresql+psycopg://scraipy_marketing:MOT_DE_PASSE@..."

User DB read-only : scraipy_marketing (SELECT uniquement sur toutes les tables)
"""

from __future__ import annotations

import html as _html
import os
import re as _re

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="SCRAIPy — Marketing",
    page_icon="👥",
    layout="wide",
)

st.title("👥 SCRAIPy — Contacts qualifiés")


# ── DB connection ─────────────────────────────────────────────────────────────

@st.cache_resource
def get_engine():
    url = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL manquant (secrets Streamlit ou .env)")
        st.stop()
    return create_engine(url, pool_pre_ping=True, pool_recycle=280)


engine = get_engine()


@st.cache_data(ttl=120)
def cached_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def query(sql: str, **params) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def scalar(sql: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar() or 0


def _build_group(conds: list[str], mode: str) -> str | None:
    if not conds:
        return None
    op = " AND " if mode == "ET" else " OR "
    return "(" + op.join(conds) + ")"


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Projet")
    try:
        projects = ["Tous"] + cached_query(
            "SELECT DISTINCT project FROM qualified_leads ORDER BY project"
        )["project"].tolist()
    except Exception:
        projects = ["Tous"]
    project_filter = st.selectbox("Projet", projects)

    st.divider()
    if st.button("🔄 Rafraîchir"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Données rafraîchies toutes les 2 min.")

proj_clause = "" if project_filter == "Tous" else f" AND project = '{project_filter}'"
ql_proj_clause = "" if project_filter == "Tous" else f" AND ql.project = '{project_filter}'"


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_home, tab_entreprises, tab_contacts, tab_guide = st.tabs([
    "🏠 Accueil",
    "🏢 Entreprises",
    "👥 Contacts",
    "📖 Guide",
])


# ── ACCUEIL ───────────────────────────────────────────────────────────────────

with tab_home:
    st.subheader("Vue d'ensemble")

    _live = f"status != 'merged'{proj_clause}"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏢 Entreprises confirmées", scalar(f"SELECT COUNT(*) FROM targets WHERE status='confirmed'{proj_clause}"))
    c2.metric("🟢 Élus CSE",              scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND cse_status='oui'"))
    c3.metric("📧 Avec email",            scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND email IS NOT NULL"))
    c4.metric("📞 Avec téléphone",        scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND phone IS NOT NULL"))

    st.divider()
    st.subheader("Contacts qualifiés")

    m1, m2, m3 = st.columns(3)
    m1.metric("🟢 Élus CSE (oui)",       scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND cse_status='oui'"))
    m2.metric("🔵 Syndiqués (oui)",       scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND union_status='oui'"))
    m3.metric("⚪ Statut inconnu",        scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND cse_status='inconnu'"))

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


# ── ENTREPRISES ───────────────────────────────────────────────────────────────

with tab_entreprises:
    _t_mode = st.radio("Mode filtres", ["ET", "OU"], horizontal=True, key="t_mode",
                       help="ET = tous les critères requis. OU = au moins un suffit.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        t_status_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT status FROM targets ORDER BY status"
        )["status"].tolist()
        target_status = st.selectbox("Statut", t_status_opts, key="t_status")
    with col2:
        naf_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT naf_code FROM targets WHERE naf_code IS NOT NULL ORDER BY naf_code"
        )["naf_code"].tolist()
        target_naf = st.selectbox("Code NAF", naf_opts, key="t_naf")
    with col3:
        bracket_opts = ["Tous"] + cached_query(
            "SELECT DISTINCT headcount_bracket FROM targets WHERE headcount_bracket IS NOT NULL ORDER BY headcount_bracket"
        )["headcount_bracket"].tolist()
        target_bracket = st.selectbox("Tranche effectif", bracket_opts, key="t_bracket")
    with col4:
        target_search = st.text_input("Recherche nom / SIREN", placeholder="ex: EDF, 552081317…")

    _t_fixed = ["1=1"]
    _t_dynamic: list[str] = []
    if project_filter != "Tous":
        _t_fixed.append(f"project = '{project_filter}'")
    if target_status != "Tous":
        _t_dynamic.append(f"status = '{target_status}'")
    if target_naf != "Tous":
        _t_dynamic.append(f"naf_code = '{target_naf}'")
    if target_bracket != "Tous":
        _t_dynamic.append(f"headcount_bracket = '{target_bracket}'")
    if target_search:
        safe = target_search.replace("'", "''")
        _t_dynamic.append(f"(label ILIKE '%{safe}%' OR siren = '{safe}')")
    _t_groups = [g for g in [_build_group(_t_dynamic, _t_mode)] if g] if _t_dynamic else []
    t_where_sql = " AND ".join(_t_fixed + (_t_groups or []))

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
        c3.metric("⏳ En attente",  int((df_t["statut"] == "to_confirm").sum()))

    st.dataframe(df_t, use_container_width=True, hide_index=True)

    if not df_t.empty:
        csv = df_t.to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export CSV entreprises", csv, "entreprises.csv", "text/csv")


# ── CONTACTS ─────────────────────────────────────────────────────────────────

with tab_contacts:
    # Groupe 1 : Statuts
    with st.container(border=True):
        _hc, _mc = st.columns([5, 1])
        _hc.markdown("##### Groupe 1 — Statuts CSE / Syndicat")
        g1_mode = _mc.radio("Mode G1", ["ET", "OU"], horizontal=True, key="ql_g1_mode",
                             label_visibility="collapsed")
        _c1, _c2, _c3, _c4 = st.columns(4)
        cse_f     = _c1.selectbox("cse_status",   ["Tous", "oui", "non", "inconnu"], key="ql_cse")
        union_f   = _c2.selectbox("union_status",  ["Tous", "oui", "non", "inconnu"], key="ql_union")
        cse_level_f = _c3.selectbox("Instance CSE", ["Tous", "CSE", "CSEC", "(vide)"], key="ql_lvl")
        union_name_opts = ["Tous", "(vide)"] + cached_query(
            "SELECT DISTINCT union_name FROM qualified_leads WHERE union_name IS NOT NULL ORDER BY union_name"
        )["union_name"].tolist()
        union_name_f = _c4.selectbox("Syndicat", union_name_opts, key="ql_un")

    _sp1, _ic, _sp2 = st.columns([2, 2, 2])
    inter_mode = _ic.radio(
        "Combiner les groupes avec :", ["ET", "OU"], horizontal=True, key="ql_inter",
        help="Opérateur entre Groupe 1 (Statuts) et Groupe 2 (Coordonnées).",
    )

    # Groupe 2 : Coordonnées
    with st.container(border=True):
        _hc2, _mc2 = st.columns([5, 1])
        _hc2.markdown("##### Groupe 2 — Coordonnées")
        g2_mode = _mc2.radio("Mode G2", ["ET", "OU"], horizontal=True, key="ql_g2_mode",
                              label_visibility="collapsed")
        _c1, _c2, _c3 = st.columns(3)
        has_email = _c1.checkbox("email présent", key="ql_he")
        has_phone = _c2.checkbox("phone présent", key="ql_hp")
        has_name  = _c3.checkbox("nom présent",   key="ql_hn")

    st.markdown("**Contexte** *(toujours ET)*")
    _r2c1, _r2c2, _r2c3, _r2c4 = st.columns(4)
    siren_f          = _r2c1.text_input("SIREN entreprise", key="ql_siren")
    name_search      = _r2c2.text_input("Nom / email contient", key="ql_name")
    min_ev           = _r2c3.number_input("Min sources", min_value=0, max_value=20, value=0, step=1, key="ql_minev")
    source_max_years = _r2c4.number_input("Source < X ans (0=off)", min_value=0, max_value=20, value=0, step=1, key="ql_freshness")
    limit_ql         = st.number_input("Limite résultats", min_value=50, max_value=5000, value=500, step=50, key="ql_lim")

    # Build WHERE
    where: list[str] = ["ql.status != 'merged'"]
    if project_filter != "Tous":
        where.append(f"ql.project = '{project_filter}'")

    _g1: list[str] = []
    if cse_f != "Tous":
        _g1.append(f"ql.cse_status = '{cse_f}'")
    if union_f != "Tous":
        _g1.append(f"ql.union_status = '{union_f}'")
    if cse_level_f == "(vide)":
        _g1.append("ql.cse_level IS NULL")
    elif cse_level_f != "Tous":
        _g1.append(f"ql.cse_level = '{cse_level_f}'")
    if union_name_f == "(vide)":
        _g1.append("ql.union_name IS NULL")
    elif union_name_f != "Tous":
        safe = union_name_f.replace("'", "''")
        _g1.append(f"ql.union_name = '{safe}'")

    _g2: list[str] = []
    if has_email:
        _g2.append("ql.email IS NOT NULL")
    if has_phone:
        _g2.append("ql.phone IS NOT NULL")
    if has_name:
        _g2.append("(ql.first_name IS NOT NULL OR ql.last_name IS NOT NULL)")

    _active_groups = [g for g in [_build_group(_g1, g1_mode), _build_group(_g2, g2_mode)] if g]
    if _active_groups:
        _inter_op = " AND " if inter_mode == "ET" else " OR "
        where.append("(" + _inter_op.join(_active_groups) + ")")

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

    if not df_ql.empty:
        csv = df_ql.drop(columns=["id"]).to_csv(index=False).encode("utf-8")
        st.download_button("⬇️ Export CSV contacts", csv, "contacts_scraipy.csv", "text/csv",
                           type="primary")

    # ── Inspecteur contact (clic sur ligne) ──────────────────────────────────
    sel_id = ""
    if event.selection and event.selection.rows:
        sel_id = str(df_ql.iloc[event.selection.rows[0]]["id"])

    st.divider()
    if not sel_id:
        st.caption("👆 Clique une ligne pour voir les détails et les sources du contact")
    else:
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
        if not full.empty:
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
                    _url = ev.get("source_url")
                    if _url:
                        st.markdown(f"**URL** : [{_url}]({_url})")
                    else:
                        st.markdown("**URL** : *(aucune)*")
                    st.markdown(
                        f"**Date source** : {ev.get('source_date') or '?'}"
                        f" · **Collecté le** : {ev.get('collected_at') or '?'}"
                    )
                    if ev.get("snippet"):
                        st.code(ev["snippet"])

                    # Fetch captured document text for this URL
                    if _url:
                        doc_df = query(
                            """
                            SELECT parsed_text, meta->>'title' AS title,
                                   content_type, meta->>'source_date' AS source_date
                            FROM captured_documents
                            WHERE url = :url
                            ORDER BY collected_at DESC LIMIT 1
                            """,
                            url=_url,
                        )
                        if not doc_df.empty:
                            doc = doc_df.iloc[0]
                            parsed = doc["parsed_text"] or ""
                            st.caption(
                                f"📄 **{doc['title'] or ''}** · {doc['content_type']}"
                                f" · source_date: {doc['source_date']} · {len(parsed):,} chars"
                            )
                            if parsed:
                                search_term = (
                                    (row["last_name"] or row["first_name"] or "").strip()
                                )
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


# ── GUIDE ─────────────────────────────────────────────────────────────────────

with tab_guide:
    st.markdown("## 📖 Guide d'utilisation")
    st.caption("Ce dashboard permet d'explorer la base de contacts qualifiés et de l'exporter en CSV.")

    st.divider()

    with st.expander("🏠 Onglet Accueil", expanded=True):
        st.markdown("""
**Vue d'ensemble de la base.**

- Les **métriques du haut** donnent le nombre d'entreprises confirmées et de contacts selon leur statut.
- Le tableau **Élus CSE par entreprise** montre les 20 entreprises les mieux couvertes.

> *Conseil :* commencez toujours par l'Accueil pour avoir une idée de la volumétrie avant de filtrer.
""")

    with st.expander("🏢 Onglet Entreprises"):
        st.markdown("""
**Liste des entreprises du périmètre.**

| Colonne | Signification |
|---|---|
| `statut` | `confirmed` = entreprise validée dans le périmètre |
| `tranche_effectif` | Tranche INSEE (ex: `5001_10000` = 5 000 à 10 000 salariés) |
| `naf_code` | Code activité (ex: `35.11Z` = production d'électricité) |

**Filtres disponibles :** statut, code NAF, tranche effectif, recherche par nom ou SIREN.

**Mode ET / OU** : avec *ET* tous les filtres doivent correspondre ; avec *OU* un seul suffit.

Le bouton **⬇️ Export CSV entreprises** télécharge la liste filtrée.
""")

    with st.expander("👥 Onglet Contacts — les filtres"):
        st.markdown("""
**Recherche en deux groupes combinables.**

#### Groupe 1 — Statuts CSE / Syndicat
Filtre sur le type de contact :

| Champ | Valeurs |
|---|---|
| `cse_status` | `oui` = élu·e au CSE · `inconnu` = statut non confirmé |
| `union_status` | `oui` = syndiqué·e confirmé·e |
| Instance CSE | `CSE` (établissement) · `CSEC` (central) |
| Syndicat | CFDT, CGT, FO, CFE-CGC… |

#### Groupe 2 — Coordonnées
Filtre sur la présence des données de contact : email, téléphone, nom.

#### Combiner les groupes
Le radio **"Combiner les groupes avec : ET / OU"** entre les deux blocs définit comment ils s'articulent.

**Exemples concrets :**

| Objectif | Réglage |
|---|---|
| Tous les élus CSE *ou* syndiqués | G1 : `cse=oui` + `union=oui`, mode G1 = **OU** |
| Élus CSE qu'on peut contacter | G1 : `cse=oui`, G2 : email ✓, inter = **ET** |
| N'importe qui avec email *ou* téléphone | G2 : email ✓ + phone ✓, mode G2 = **OU** |
| Élus CSE *ou* syndiqués avec coordonnées | G1 : `cse=oui`+`union=oui` mode **OU**, G2 : email ✓ mode **OU**, inter = **ET** |

#### Contexte (toujours ET)
- **SIREN entreprise** : restreindre à une entreprise précise
- **Nom / email contient** : recherche libre sur le nom ou l'adresse email
- **Min sources** : n'afficher que les contacts avec au moins N sources (plus fiable = plus élevé)
- **Source < X ans** : exclure les données trop anciennes (ex: 3 = sources de moins de 3 ans)
""")

    with st.expander("👥 Onglet Contacts — l'inspecteur"):
        st.markdown("""
**Cliquer une ligne du tableau** ouvre l'inspecteur détaillé en bas de page.

Il affiche :
- **Coordonnées** complètes (email, téléphone, statuts CSE/Syndicat, mandat)
- **Entreprise** (nom, SIREN, niveau de confiance)
- **Sources** : chaque source ayant permis d'identifier ce contact

Pour chaque source, un **extrait du document original** est affiché avec le nom du contact surligné en jaune. Cela permet de vérifier le contexte (page web, PDF de résultats électoraux, etc.).

> *Conseil :* le nombre de sources (`nb_sources`) est un bon indicateur de fiabilité. Un contact avec 3+ sources est très probablement correct.
""")

    with st.expander("⬇️ Export CSV"):
        st.markdown("""
Le bouton **⬇️ Export CSV contacts** télécharge tous les contacts correspondant aux filtres actifs (dans la limite d'affichage).

**Conseil avant d'exporter :**
1. Vérifiez les métriques (total filtres, avec email, avec téléphone) pour estimer la volumétrie
2. Si le total dépasse la limite d'affichage (500 par défaut), augmentez la **Limite résultats** dans le contexte

Le fichier CSV est encodé en UTF-8 et s'ouvre directement dans Excel ou Google Sheets.
""")

    with st.expander("🔄 Données & mise à jour"):
        st.markdown("""
- Les données sont **rafraîchies automatiquement toutes les 2 minutes**.
- Le bouton **🔄 Rafraîchir** en sidebar force un rechargement immédiat.
- La base est alimentée en continu par le pipeline SCRAIPy — de nouveaux contacts peuvent apparaître d'une session à l'autre.
- Accès **lecture seule** : aucune modification n'est possible depuis ce dashboard.
""")
