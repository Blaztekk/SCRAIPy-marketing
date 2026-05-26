"""Pandas reimplementation of the composite scoring formula.

Why a parallel pandas implementation : when the campaign context (camp_union /
camp_company) is injected into the SQL string, every change invalidates the
@st.cache_data key and forces a full Neon round-trip (~0.5-1s from France).
Computing the score in pandas instead lets us cache one stable SQL query
(per project) and recompute scores instantly in memory when the user toggles
campaign or segment filters.

Keep this formula in sync with scoring.build_score_sql / build_score_popover_md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from marketing.scoring import NONE_COMPANY, NONE_UNION

_ROLE_BUREAU_PATTERN = r"secrétaire|trésorier|trésorière|président"
_ROLE_TITULAIRE_PATTERN = r"titulaire|membre"


def compute_score(
    df: pd.DataFrame,
    camp_union: str = NONE_UNION,
    camp_company: str = NONE_COMPANY,
) -> pd.Series:
    """Compute composite score per row.

    Expected columns : role, phone, email, cse_status, source_date,
    nb_sources, syndicat, entreprise.
    """
    if df.empty:
        return pd.Series(dtype="int64")

    role = df["role"].fillna("").astype(str)
    phone = df["phone"].fillna("").astype(str)

    bureau = role.str.contains(_ROLE_BUREAU_PATTERN, case=False, regex=True, na=False)
    titulaire = role.str.contains(_ROLE_TITULAIRE_PATTERN, case=False, regex=True, na=False)
    role_score = np.where(bureau, 7, np.where(titulaire, 3, 0))

    cse_score = (df["cse_status"] == "oui").astype(int) * 10
    email_score = df["email"].notna().astype(int) * 5
    phone_score = df["phone"].notna().astype(int) * 3
    mobile_score = phone.str.startswith(("06", "07")).astype(int) * 2
    sources_score = df["nb_sources"].clip(upper=5).fillna(0).astype(int)

    two_years_ago = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=730)
    source_dt = pd.to_datetime(df["source_date"], utc=True, errors="coerce")
    fresh_score = (source_dt >= two_years_ago).astype(int) * 2

    if "bouncer_status" in df.columns:
        bouncer = df["bouncer_status"].fillna("").astype(str)
        bouncer_penalty = (
            (bouncer == "risky").astype(int) * -5
            + (bouncer == "unknown").astype(int) * -3
        )
    else:
        bouncer_penalty = 0

    score = (
        cse_score
        + role_score
        + email_score
        + phone_score
        + mobile_score
        + sources_score
        + fresh_score
        + bouncer_penalty
    )

    if camp_union and camp_union != NONE_UNION:
        syndicat = df["syndicat"].fillna("").astype(str)
        score = score + syndicat.str.contains(
            camp_union, case=False, regex=False, na=False
        ).astype(int) * 3

    if camp_company and camp_company != NONE_COMPANY:
        employeur = df["entreprise"].fillna("").astype(str)
        score = score + employeur.str.contains(
            camp_company, case=False, regex=False, na=False
        ).astype(int) * 3

    return score.astype(int)
