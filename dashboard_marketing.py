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

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="SCRAIPy — Contacts",
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
def run_query(sql: str, params: dict | None = None) -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


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
        projects = ["Tous"] + run_query(
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


# ── Métriques globales ────────────────────────────────────────────────────────

proj_clause = "" if project_filter == "Tous" else f" AND project = '{project_filter}'"
_live = f"status != 'merged'{proj_clause}"

col1, col2, col3, col4 = st.columns(4)
col1.metric("🟢 Élus CSE",        scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND cse_status='oui'"))
col2.metric("🔵 Syndiqués",        scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND union_status='oui'"))
col3.metric("📧 Avec email",       scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND email IS NOT NULL"))
col4.metric("📞 Avec téléphone",   scalar(f"SELECT COUNT(*) FROM qualified_leads WHERE {_live} AND phone IS NOT NULL"))

st.divider()

# ── Filtres ───────────────────────────────────────────────────────────────────

# Groupe 1 : Statuts
with st.container(border=True):
    _hc, _mc = st.columns([5, 1])
    _hc.markdown("##### Groupe 1 — Statuts CSE / Syndicat")
    g1_mode = _mc.radio("Mode G1", ["ET", "OU"], horizontal=True, key="g1_mode",
                         label_visibility="collapsed")
    _c1, _c2, _c3 = st.columns(3)
    cse_f     = _c1.selectbox("cse_status",   ["Tous", "oui", "non", "inconnu"], key="cse_f")
    union_f   = _c2.selectbox("union_status", ["Tous", "oui", "non", "inconnu"], key="union_f")
    try:
        un_opts = ["Tous", "(vide)"] + run_query(
            "SELECT DISTINCT union_name FROM qualified_leads "
            "WHERE union_name IS NOT NULL ORDER BY union_name"
        )["union_name"].tolist()
    except Exception:
        un_opts = ["Tous"]
    union_name_f = _c3.selectbox("Syndicat", un_opts, key="union_name_f")

# Inter-groupe
_sp1, _ic, _sp2 = st.columns([2, 2, 2])
inter_mode = _ic.radio(
    "Combiner les groupes avec :", ["ET", "OU"], horizontal=True, key="inter_mode",
    help="Opérateur entre Groupe 1 (Statuts) et Groupe 2 (Coordonnées).",
)

# Groupe 2 : Coordonnées
with st.container(border=True):
    _hc2, _mc2 = st.columns([5, 1])
    _hc2.markdown("##### Groupe 2 — Coordonnées")
    g2_mode = _mc2.radio("Mode G2", ["ET", "OU"], horizontal=True, key="g2_mode",
                          label_visibility="collapsed")
    _c1, _c2, _c3 = st.columns(3)
    has_email = _c1.checkbox("email présent", key="has_email")
    has_phone = _c2.checkbox("phone présent", key="has_phone")
    has_name  = _c3.checkbox("nom présent",   key="has_name")

# Contexte
st.markdown("**Contexte** *(toujours ET)*")
_r1, _r2, _r3, _r4 = st.columns(4)
siren_f       = _r1.text_input("SIREN employeur", key="siren_f")
name_search   = _r2.text_input("Nom / email contient", key="name_search")
min_ev        = _r3.number_input("Min evidences", min_value=0, max_value=20, value=0, step=1, key="min_ev")
limit_ql      = _r4.number_input("Limite résultats", min_value=50, max_value=5000, value=500, step=50, key="limit_ql")


# ── Build WHERE ───────────────────────────────────────────────────────────────

where: list[str] = ["ql.status != 'merged'"]
if project_filter != "Tous":
    where.append(f"ql.project = '{project_filter}'")

_g1: list[str] = []
if cse_f != "Tous":
    _g1.append(f"ql.cse_status = '{cse_f}'")
if union_f != "Tous":
    _g1.append(f"ql.union_status = '{union_f}'")
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

_active = [g for g in [_build_group(_g1, g1_mode), _build_group(_g2, g2_mode)] if g]
if _active:
    _inter_op = " AND " if inter_mode == "ET" else " OR "
    where.append("(" + _inter_op.join(_active) + ")")

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

where_sql = " AND ".join(where)


# ── Données ───────────────────────────────────────────────────────────────────

total_count: int = 0
try:
    total_count = scalar(f"""
        SELECT COUNT(*) FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE {where_sql}
    """)
except Exception as exc:
    st.error(f"Erreur requête : {exc}")

df = run_query(f"""
    SELECT
        ql.first_name                          AS prénom,
        ql.last_name                           AS nom,
        ql.email,
        ql.phone,
        ql.role,
        ql.cse_status,
        ql.cse_level,
        ql.union_status,
        ql.union_name                          AS syndicat,
        e.attributes->>'employeur'             AS employeur,
        e.attributes->>'siren'                 AS siren,
        ql.source_date,
        jsonb_array_length(ql.evidences::jsonb) AS nb_sources,
        (
            SELECT elem->>'source_url'
            FROM jsonb_array_elements(ql.evidences::jsonb) AS elem
            WHERE elem->>'source_url' IS NOT NULL
            LIMIT 1
        ) AS source_url,
        ROUND(ql.confidence::numeric, 2)       AS confiance
    FROM qualified_leads ql
    JOIN entities e ON ql.entity_id = e.id
    WHERE {where_sql}
    ORDER BY ql.cse_status='oui' DESC,
             nb_sources DESC,
             ql.collected_at DESC
    LIMIT {int(limit_ql)}
""")

# ── Affichage ─────────────────────────────────────────────────────────────────

m1, m2, m3, m4 = st.columns(4)
m1.metric(
    "Résultats (filtres)",
    total_count,
    delta=f"affichage limité à {len(df)}" if total_count > len(df) else None,
    delta_color="off",
)
if not df.empty:
    m2.metric("cse=oui", int((df["cse_status"] == "oui").sum()))
    m3.metric("avec email", int(df["email"].notna().sum()))
    m4.metric("avec téléphone", int(df["phone"].notna().sum()))

if not df.empty:
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "source_url": st.column_config.LinkColumn(
                "source",
                display_text=r"https?://(?:www\.)?([^/]+).*",
            ),
        },
    )
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Télécharger CSV",
        csv,
        file_name="contacts_scraipy.csv",
        mime="text/csv",
        type="primary",
    )
else:
    st.info("Aucun résultat avec ces filtres.")
