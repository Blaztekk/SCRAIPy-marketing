"""Composite scoring SQL builder for Rdy mail / Rdy call.

Reads campaign context (syndicat cible, entreprise cible) from session_state so
both rdy_mail.py and rdy_call.py can share the same scoring formula and popover
content without duplicating widget definitions.
"""

from __future__ import annotations

import streamlit as st

BASE_MAX = 34
CAMPAIGN_UNION_KEY = "camp_union"
CAMPAIGN_COMPANY_KEY = "camp_company"
NONE_UNION = "(aucun)"
NONE_COMPANY = "(aucune)"


def _esc(s: str) -> str:
    """SQL string-literal single-quote escape."""
    return s.replace("'", "''")


def get_campaign_context() -> tuple[str, str]:
    """Read campaign selections from session_state (set by rdy_mail expander)."""
    cu = st.session_state.get(CAMPAIGN_UNION_KEY, NONE_UNION)
    cc = st.session_state.get(CAMPAIGN_COMPANY_KEY, NONE_COMPANY)
    return cu, cc


def build_score_sql() -> str:
    """Return the composite scoring SQL expression.

    Base score : CSE(10) + role-bureau(7) / titulaire(3) + email(5)
                + phone(3) + mobile-bonus(2) + sources(<=5) + freshness(2).
    Campaign bonuses (+3 each) applied when session_state holds non-empty
    syndicat / entreprise.
    """
    cu, cc = get_campaign_context()
    camp_union_sql = (
        f"+ CASE WHEN ql.union_name ILIKE '%{_esc(cu)}%' THEN 3 ELSE 0 END"
        if cu != NONE_UNION else ""
    )
    camp_company_sql = (
        f"+ CASE WHEN e.attributes->>'employeur' ILIKE '%{_esc(cc)}%' THEN 3 ELSE 0 END"
        if cc != NONE_COMPANY else ""
    )
    return f"""
        CASE WHEN ql.cse_status = 'oui' THEN 10 ELSE 0 END
        + CASE
            WHEN ql.role ILIKE '%secrétaire%' OR ql.role ILIKE '%trésorier%' OR ql.role ILIKE '%trésorière%' OR ql.role ILIKE '%président%' THEN 7
            WHEN ql.role ILIKE '%titulaire%' OR ql.role ILIKE '%membre%' THEN 3
            ELSE 0
          END
        + CASE WHEN ql.email IS NOT NULL THEN 5 ELSE 0 END
        + CASE WHEN ql.phone IS NOT NULL THEN 3 ELSE 0 END
        + CASE WHEN ql.phone ILIKE '06%' OR ql.phone ILIKE '07%' THEN 2 ELSE 0 END
        + LEAST(jsonb_array_length(ql.evidences::jsonb), 5)
        + CASE WHEN ql.source_date >= NOW() - INTERVAL '2 years' THEN 2 ELSE 0 END
        + CASE WHEN ql.meta->>'bouncer_status' = 'risky' THEN -5 ELSE 0 END
        + CASE WHEN ql.meta->>'bouncer_status' = 'unknown' THEN -3 ELSE 0 END
        {camp_union_sql}
        {camp_company_sql}
    """


def build_score_popover_md() -> str:
    """Markdown shown in the ℹ️ popover next to score-sorted tables."""
    cu, cc = get_campaign_context()
    rows = ""
    if cu != NONE_UNION:
        rows += f"\n| Syndicat **{cu}** *(campagne)* | +3 |"
    if cc != NONE_COMPANY:
        rows += f"\n| Entreprise **{cc}** *(campagne)* | +3 |"
    score_max = BASE_MAX + (3 if cu != NONE_UNION else 0) + (3 if cc != NONE_COMPANY else 0)
    return f"""**Score composite — max {score_max} pts**

| Critère | Points |
|---|---|
| `cse_status = oui` | +10 |
| Rôle **bureau** (Secrétaire / Trésorier·e / Président) | +7 |
| Rôle **titulaire** ou membre | +3 |
| Email présent | +5 |
| Téléphone présent | +3 |
| Téléphone **mobile** (06/07) | +2 |
| Nb sources (plafonné à 5) | +1 à +5 |
| Source < 2 ans | +2 |
| Bouncer **risky** (SMTP douteux) | −5 |
| Bouncer **unknown** (SMTP indéterminé) | −3 |{rows}

> Score élevé = décideur joignable avec données fraîches. Commencez par le haut.
"""


def render_campaign_expander(cached_query) -> None:
    """Render the campaign-context selectboxes inside an expander.

    Call this from rdy_mail.py (the canonical location). rdy_call.py reads
    via get_campaign_context() instead — Streamlit forbids the same widget key
    in two tabs.
    """
    with st.expander("🎯 Contexte campagne — bonus scoring", expanded=False):
        _cu, _cc = st.columns(2)
        union_opts = [NONE_UNION] + cached_query(
            "SELECT DISTINCT union_name FROM qualified_leads WHERE union_name IS NOT NULL ORDER BY union_name"
        )["union_name"].tolist()
        _cu.selectbox("Syndicat cible", union_opts, key=CAMPAIGN_UNION_KEY,
                      help="+3 pts pour les contacts de ce syndicat")
        company_opts = [NONE_COMPANY] + cached_query(
            "SELECT DISTINCT attributes->>'employeur' AS employeur FROM entities "
            "WHERE attributes->>'employeur' IS NOT NULL ORDER BY employeur"
        )["employeur"].tolist()
        _cc.selectbox("Entreprise cible", company_opts, key=CAMPAIGN_COMPANY_KEY,
                      help="+3 pts pour les contacts de cette entreprise")


def render_campaign_indicator() -> None:
    """Compact read-only indicator showing active campaign context.

    Use in rdy_call.py (and anywhere else that needs to display the context
    without re-rendering the widgets).
    """
    cu, cc = get_campaign_context()
    if cu == NONE_UNION and cc == NONE_COMPANY:
        st.caption("🎯 Contexte campagne : *aucun* — configurer dans **Rdy mail**.")
        return
    parts = []
    if cu != NONE_UNION:
        parts.append(f"Syndicat **{cu}** (+3)")
    if cc != NONE_COMPANY:
        parts.append(f"Entreprise **{cc}** (+3)")
    st.caption("🎯 " + " · ".join(parts) + " — *modifier dans **Rdy mail***.")
