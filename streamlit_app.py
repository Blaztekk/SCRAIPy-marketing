"""SCRAIPy — Marketing Explorer (read-only, public).

Entry point for the public marketing dashboard.

Run locally :
    streamlit run dashboard/marketing/streamlit_app.py

Deploy : copy dashboard/shared/ and dashboard/marketing/ to the public repo
(https://github.com/Blaztekk/SCRAIPy-marketing) via dashboard/deploy.ps1.
Streamlit Cloud auto-detects this file as the entry point.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make `shared.*` and `marketing.*` resolvable in both layouts:
#   - local dev   : __file__ = SCRAIPy/dashboard/marketing/streamlit_app.py
#                   → root = SCRAIPy/dashboard/      (has shared/ + marketing/)
#   - Streamlit Cloud (deployed flat) :
#                   __file__ = SCRAIPy-marketing/streamlit_app.py
#                   → root = SCRAIPy-marketing/      (has shared/ + marketing/)
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent if (_HERE.parent / "shared").is_dir() else _HERE
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st  # noqa: E402  -- must come after sys.path tweak

st.set_page_config(
    page_title="SCRAIPy — Marketing",
    page_icon="👥",
    layout="wide",
)
st.title("👥 SCRAIPy — Contacts qualifiés")

from shared.db import make_cached_query, query, scalar  # noqa: E402
from marketing.tabs import entreprises, guide, home  # noqa: E402
from marketing.tabs.contacts import render as render_contacts  # noqa: E402

cached_query = make_cached_query(ttl=120)


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

proj_clause    = "" if project_filter == "Tous" else f" AND project = '{project_filter}'"
ql_proj_clause = "" if project_filter == "Tous" else f" AND ql.project = '{project_filter}'"


# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_home, tab_entreprises, tab_contacts, tab_guide = st.tabs([
    "🏠 Accueil",
    "🏢 Entreprises",
    "👥 Contacts",
    "📖 Guide",
])

with tab_home:
    home.render(scalar, cached_query, proj_clause, ql_proj_clause)

with tab_entreprises:
    entreprises.render(scalar, cached_query, project_filter)

with tab_contacts:
    render_contacts(scalar, cached_query, query, project_filter)

with tab_guide:
    guide.render()
