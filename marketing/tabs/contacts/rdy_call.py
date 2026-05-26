"""Rdy call — leads avec téléphone confirmé.

Reads campaign context from session_state (widgets live in rdy_mail).
Same perf model as rdy_mail : one stable SQL query per project, score + filters
applied in pandas. See rdy_mail.py for details.
"""

from __future__ import annotations

import streamlit as st

from marketing.exports import get_excluded_ids, render_export_block
from marketing.scoring import (
    build_score_popover_md,
    get_campaign_context,
    render_campaign_indicator,
)
from marketing.scoring_pandas import compute_score

CHANNEL = "call"
DISPLAY_LIMIT = 1000


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
    c1, c2, c3 = st.columns(3)
    also_email = c1.checkbox(
        "Possède aussi un email", value=False, key="rc_also_email"
    )
    exclude_bouncer_doubt = c2.checkbox(
        "Exclure SMTP email douteux (risky / unknown)",
        value=True, key="rc_excl_bouncer",
        help="Filtre les leads dont l'email a un statut Bouncer risky / unknown "
             "(même si on cible le téléphone — un mauvais email signale souvent "
             "une source à risque).",
    )
    excluded_ids = get_excluded_ids(CHANNEL)
    hide_exported = c3.checkbox(
        f"Masquer déjà exportés ({len(excluded_ids)})",
        value=True, key="rc_hide_exported",
        help="Masque les leads déjà tagués sur le canal call.",
    )

    df = _fetch_pool(cached_query, project_filter)
    df = _apply_filters(
        df, seg=seg, also_email=also_email,
        exclude_bouncer_doubt=exclude_bouncer_doubt,
    )
    df = _score_and_sort(df)
    if hide_exported and excluded_ids:
        df = df[~df["_lead_id"].isin(excluded_ids)].reset_index(drop=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Leads prêts (tél.)", len(df))
    if not df.empty:
        m2.metric("CSE=oui",     int((df["cse_status"] == "oui").sum()))
        m3.metric("Aussi email", int(df["email"].notna().sum()))
        m4.metric("Score moyen", round(float(df["score"].mean()), 1))

    st.dataframe(
        df.drop(columns=["_lead_id"]).head(DISPLAY_LIMIT),
        use_container_width=True,
        hide_index=True,
    )

    if not df.empty:
        render_export_block(df, channel=CHANNEL, key_prefix="rc")


def _fetch_pool(cached_query, project_filter: str):
    """One stable SQL : phone IS NOT NULL + project. No score, no seg, no also."""
    proj_clause = "" if project_filter == "Tous" else f" AND ql.project = '{project_filter}'"
    return cached_query(f"""
        SELECT
            ql.id                                        AS _lead_id,
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
            ql.source_date,
            ql.meta->>'bouncer_status'                   AS bouncer_status
        FROM qualified_leads ql
        JOIN entities e ON ql.entity_id = e.id
        WHERE ql.status != 'merged'
          AND ql.phone IS NOT NULL
          AND COALESCE(ql.meta->>'name_suspicious', 'false') <> 'true'
          {proj_clause}
    """)


def _apply_filters(df, *, seg: str, also_email: bool, exclude_bouncer_doubt: bool):
    if df.empty:
        return df
    if seg == "CSE uniquement":
        df = df[df["cse_status"] == "oui"]
    elif seg == "Syndiqué uniquement":
        df = df[df["union_status"] == "oui"]
    if also_email:
        df = df[df["email"].notna()]
    if exclude_bouncer_doubt and "bouncer_status" in df.columns:
        df = df[~df["bouncer_status"].isin(["risky", "unknown"])]
    return df


def _score_and_sort(df):
    if df.empty:
        df = df.copy()
        df["score"] = []
        return df
    cu, cc = get_campaign_context()
    df = df.copy()
    df["score"] = compute_score(df, camp_union=cu, camp_company=cc)
    return df.sort_values(
        ["score", "nb_sources"], ascending=[False, False]
    ).reset_index(drop=True)
