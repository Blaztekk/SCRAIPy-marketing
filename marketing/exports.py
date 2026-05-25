"""Campaign export tagging — write side of the marketing dashboard.

The marketing dashboard is read-only **except** for this module, which UPSERTs
rows into `lead_exports` so users can pull "top N by score, excluding leads
already exported on this channel" without duplicating outreach.

One row per (lead_id, channel). Re-exporting the same lead on the same channel
updates exported_at + batch_id. batch_id groups the N rows of a single export
click — useful for audit ("which 100 leads went out at 13:42").

UX : the tab shows a single "⬇️ Télécharger CSV…" button. Click opens a modal
dialog where the user picks params (exclude already tagged / N / Explorer vs
Travailler mode) and triggers the actual download — tag posed only on the
Travailler path.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pandas as pd
import streamlit as st
from sqlalchemy import text

from shared.db import get_engine

VALID_CHANNELS = ("email", "call")

MODE_EXPLORE = "🧪 Explorer / tester (no tag)"
MODE_WORK = "🎯 Travailler les contacts (tag définitif)"


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


def render_export_block(
    df: pd.DataFrame,
    *,
    channel: str,
    key_prefix: str,
    id_col: str = "_lead_id",
) -> None:
    """Render a single 'Télécharger CSV…' button that opens the export modal."""
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CHANNELS}, got {channel!r}")

    st.divider()
    excluded = get_excluded_ids(channel)
    st.caption(
        f"📤 Export campagne **{channel}** · Pool affiché : {len(df)} leads · "
        f"{len(excluded)} déjà tagués sur ce canal"
    )

    if st.button(
        "⬇️ Télécharger CSV…",
        key=f"{key_prefix}_open_dialog",
        type="primary",
        disabled=df.empty,
        use_container_width=False,
    ):
        _export_dialog(
            df=df,
            channel=channel,
            key_prefix=key_prefix,
            id_col=id_col,
        )

    if st.session_state.get(f"{key_prefix}_csv"):
        st.success(
            f"✅ {st.session_state[f'{key_prefix}_count']} leads tagués · "
            f"batch `{st.session_state[f'{key_prefix}_batch']}`"
        )
        st.download_button(
            f"⬇️ Re-télécharger {st.session_state[f'{key_prefix}_fname']}",
            st.session_state[f"{key_prefix}_csv"],
            st.session_state[f"{key_prefix}_fname"],
            "text/csv",
            key=f"{key_prefix}_dl_after_tag",
        )


@st.dialog("📤 Export campagne — paramètres", width="large")
def _export_dialog(
    *,
    df: pd.DataFrame,
    channel: str,
    key_prefix: str,
    id_col: str,
) -> None:
    """Modal containing all export params + the actual download/tag action."""
    excluded = get_excluded_ids(channel)
    df_pool = df[~df[id_col].isin(excluded)] if excluded else df

    st.markdown(f"### Canal : **`{channel}`**")

    exclude = st.checkbox(
        f"Exclure déjà exportés ({channel}) — {len(excluded)} leads",
        value=True,
        key=f"{key_prefix}_dlg_exclude",
    )
    pool = df_pool if exclude else df
    n_max = max(len(pool), 1)
    n = st.number_input(
        "Nb lignes à exporter",
        min_value=1,
        max_value=n_max,
        value=min(100, n_max),
        step=10,
        key=f"{key_prefix}_dlg_n",
    )

    mode = st.radio(
        "Mode",
        [MODE_EXPLORE, MODE_WORK],
        index=0,
        key=f"{key_prefix}_dlg_mode",
        help=(
            "Explorer : télécharge le CSV sans rien marquer en base — "
            "pour inspecter, partager un échantillon, tester un ciblage.\n\n"
            "Travailler : tag les leads comme exportés sur ce canal. "
            "Ils seront exclus par défaut des prochains exports du même canal."
        ),
    )

    top_n = pool.head(int(n))
    csv_df = top_n.drop(columns=[id_col])
    csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
    fname = f"rdy_{channel}.csv"
    lead_ids = top_n[id_col].tolist()

    st.caption(
        f"Pool : {len(pool)} leads ({'hors déjà exportés' if exclude else 'tous'}) "
        f"· Sélection : top {len(top_n)}"
    )

    sample_cols = [c for c in ("prénom", "nom", "score", "entreprise") if c in top_n.columns]
    with st.expander(f"👁️ Aperçu (top 5 sur {len(top_n)})", expanded=False):
        st.dataframe(top_n[sample_cols].head(5), use_container_width=True, hide_index=True)

    st.divider()

    if mode == MODE_EXPLORE:
        st.warning("🧪 **Mode test** — aucun lead ne sera marqué en base.")
        col_dl, col_cancel = st.columns([2, 1])
        col_dl.download_button(
            f"⬇️ Télécharger ({len(top_n)} lignes)",
            csv_bytes,
            fname,
            "text/csv",
            type="primary",
            key=f"{key_prefix}_dlg_dl_explore",
            disabled=top_n.empty,
            use_container_width=True,
        )
        if col_cancel.button(
            "❌ Fermer",
            key=f"{key_prefix}_dlg_cancel_explore",
            use_container_width=True,
        ):
            st.rerun()
    else:
        st.warning(
            f"⚠️ **Mode Travailler** — les {len(lead_ids)} leads seront marqués "
            f"`{channel}=exporté` en base et exclus par défaut des futurs "
            "exports de ce canal."
        )
        col_confirm, col_cancel = st.columns([2, 1])
        if col_confirm.button(
            f"🎯 Confirmer + tagger {len(lead_ids)} leads",
            type="primary",
            key=f"{key_prefix}_dlg_confirm",
            disabled=not lead_ids,
            use_container_width=True,
        ):
            batch_id = record_export(lead_ids, channel)
            st.session_state[f"{key_prefix}_csv"] = csv_bytes
            st.session_state[f"{key_prefix}_fname"] = fname
            st.session_state[f"{key_prefix}_batch"] = str(batch_id)
            st.session_state[f"{key_prefix}_count"] = len(lead_ids)
            st.rerun()
        if col_cancel.button(
            "❌ Annuler",
            key=f"{key_prefix}_dlg_cancel_work",
            use_container_width=True,
        ):
            st.rerun()
