"""Campaign export tagging — write side of the marketing dashboard.

The marketing dashboard is read-only **except** for this module, which UPSERTs
rows into `lead_exports` so users can pull "top N by score, excluding leads
already exported on this channel" without duplicating outreach.

One row per (lead_id, channel). Re-exporting the same lead on the same channel
updates exported_at + batch_id. batch_id groups the N rows of a single export
click — useful for audit ("which 100 leads went out at 13:42").
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pandas as pd
import streamlit as st
from sqlalchemy import text

from shared.db import get_engine

VALID_CHANNELS = ("email", "call")


@st.cache_data(ttl=60, show_spinner=False)
def get_excluded_ids(channel: str) -> set[UUID]:
    """Return set of QualifiedLead ids already tagged on `channel`.

    Cached 60s. Invalidated by record_export() via .clear() so a fresh tag
    appears in the next exclusion list without waiting for TTL.
    """
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CHANNELS}, got {channel!r}")
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT lead_id FROM lead_exports WHERE channel = :ch"),
            {"ch": channel},
        ).fetchall()
    return {row[0] for row in rows}


def record_export(lead_ids: list[UUID] | list[str], channel: str) -> UUID:
    """UPSERT lead_exports rows for the given leads on `channel`.

    Returns the batch_id assigned to this export (every row shares it).
    Re-exporting an already-tagged lead refreshes its exported_at + batch_id
    (we keep one row per (lead, channel) — see uq_lead_exports_lead_channel).
    """
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CHANNELS}, got {channel!r}")
    if not lead_ids:
        raise ValueError("lead_ids cannot be empty")

    batch_id = uuid4()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO lead_exports (id, lead_id, channel, exported_at, batch_id)
                SELECT gen_random_uuid(), CAST(:lead_id AS uuid), :ch, NOW(), :batch_id
                ON CONFLICT (lead_id, channel) DO UPDATE
                SET exported_at = EXCLUDED.exported_at,
                    batch_id    = EXCLUDED.batch_id
                """
            ),
            [
                {"lead_id": str(lid), "ch": channel, "batch_id": str(batch_id)}
                for lid in lead_ids
            ],
        )
    get_excluded_ids.clear()
    return batch_id


@st.fragment
def render_export_block(
    df: pd.DataFrame,
    *,
    channel: str,
    key_prefix: str,
    id_col: str = "_lead_id",
) -> None:
    """Render the campaign export UI block under a Rdy mail / Rdy call table.

    Expects `df` already sorted by score DESC and to contain `id_col`
    (QualifiedLead UUID, dropped before display/CSV). The "exclude already
    exported" toggle pre-checks the SAME channel only (call tab doesn't
    pre-exclude email and vice versa).
    """
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CHANNELS}, got {channel!r}")

    st.divider()
    st.subheader(f"📤 Export campagne — {channel}")

    excluded = get_excluded_ids(channel)
    df_pool = df[~df[id_col].isin(excluded)] if excluded else df

    c1, c2, c3 = st.columns([2, 2, 3])
    exclude = c1.checkbox(
        f"Exclure déjà exportés ({channel}) — {len(excluded)} leads",
        value=True,
        key=f"{key_prefix}_exclude",
    )
    pool = df_pool if exclude else df
    n_max = max(len(pool), 1)
    n = c2.number_input(
        "Nb lignes à exporter",
        min_value=1,
        max_value=n_max,
        value=min(100, n_max),
        step=10,
        key=f"{key_prefix}_n",
    )
    apply_tag = c3.radio(
        "Marquer comme exportés ?",
        ["Oui", "Non"],
        index=0,
        horizontal=True,
        key=f"{key_prefix}_tag",
    )

    top = pool.head(int(n)).drop(columns=[id_col])
    lead_ids = pool.head(int(n))[id_col].tolist()
    st.caption(
        f"Pool : {len(pool)} leads ({'hors déjà exportés' if exclude else 'tous'}) "
        f"· Export : top {len(top)}"
    )

    csv = top.to_csv(index=False).encode("utf-8")
    fname = f"rdy_{channel}.csv"

    if apply_tag == "Oui":
        col_a, col_b = st.columns([1, 1])
        if col_a.button(
            f"📌 Tagger {len(lead_ids)} leads + préparer CSV",
            key=f"{key_prefix}_tag_btn",
            type="primary",
            disabled=not lead_ids,
        ):
            batch_id = record_export(lead_ids, channel)
            st.session_state[f"{key_prefix}_csv"] = csv
            st.session_state[f"{key_prefix}_fname"] = fname
            st.session_state[f"{key_prefix}_batch"] = str(batch_id)
            st.success(f"{len(lead_ids)} leads tagués · batch {batch_id}")
            st.rerun()
        if st.session_state.get(f"{key_prefix}_csv"):
            col_b.download_button(
                f"⬇️ Télécharger {st.session_state[f'{key_prefix}_fname']}",
                st.session_state[f"{key_prefix}_csv"],
                st.session_state[f"{key_prefix}_fname"],
                "text/csv",
                key=f"{key_prefix}_dl_tagged",
            )
            st.caption(f"batch_id : `{st.session_state[f'{key_prefix}_batch']}`")
    else:
        st.download_button(
            f"⬇️ Télécharger sans tag — top {len(top)}",
            csv,
            fname,
            "text/csv",
            type="primary",
            key=f"{key_prefix}_dl_notag",
            disabled=top.empty,
        )
