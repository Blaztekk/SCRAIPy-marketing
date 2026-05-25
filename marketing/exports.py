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
    """Render the campaign export UI block under a Rdy mail / Rdy call table.

    Two modes :
      - Explorer / tester : download CSV only, no DB write.
      - Travailler        : click → modal dialog with récap + confirm/cancel.
                            Tag posed only on confirm.

    Expects `df` already sorted by score DESC and to contain `id_col`
    (QualifiedLead UUID, dropped before display/CSV). The "exclude already
    exported" toggle pre-checks the SAME channel only.
    """
    if channel not in VALID_CHANNELS:
        raise ValueError(f"channel must be one of {VALID_CHANNELS}, got {channel!r}")

    st.divider()
    st.subheader(f"📤 Export campagne — {channel}")

    excluded = get_excluded_ids(channel)
    df_pool = df[~df[id_col].isin(excluded)] if excluded else df

    c1, c2 = st.columns([3, 2])
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

    top_n = pool.head(int(n))
    csv_df = top_n.drop(columns=[id_col])
    lead_ids = top_n[id_col].tolist()
    st.caption(
        f"Pool : {len(pool)} leads ({'hors déjà exportés' if exclude else 'tous'}) "
        f"· Export : top {len(top_n)}"
    )

    csv_bytes = csv_df.to_csv(index=False).encode("utf-8")
    fname = f"rdy_{channel}.csv"

    with st.container(border=True):
        mode = st.radio(
            "Mode",
            [MODE_EXPLORE, MODE_WORK],
            index=0,
            key=f"{key_prefix}_mode",
            help=(
                "Explorer : télécharge le CSV sans rien marquer en base — "
                "pour inspecter, partager un échantillon, tester un ciblage.\n\n"
                "Travailler : tag les leads comme exportés (canal "
                f"{channel}). Ils seront exclus par défaut des futurs exports "
                "du même canal. À utiliser quand on s'apprête à les contacter."
            ),
        )

        if mode == MODE_EXPLORE:
            st.download_button(
                f"⬇️ Télécharger sans tag — top {len(top_n)}",
                csv_bytes,
                fname,
                "text/csv",
                type="primary",
                key=f"{key_prefix}_dl_explore",
                disabled=top_n.empty,
            )
        else:
            st.warning(
                "⚠️ **Mode Travailler — tag définitif.** "
                f"Une fois validés, les {len(lead_ids)} leads seront marqués "
                f"`{channel}=exporté` en base et exclus par défaut des futurs "
                "exports de ce canal. La confirmation passe par une pop-up."
            )
            if st.button(
                f"🎯 Tagger {len(lead_ids)} leads + préparer CSV",
                key=f"{key_prefix}_open_dialog",
                type="primary",
                disabled=not lead_ids,
            ):
                _confirm_export_dialog(
                    pool=pool,
                    top_n=top_n,
                    lead_ids=lead_ids,
                    channel=channel,
                    csv_bytes=csv_bytes,
                    fname=fname,
                    key_prefix=key_prefix,
                )

    if st.session_state.get(f"{key_prefix}_csv"):
        st.success(
            f"✅ {st.session_state[f'{key_prefix}_count']} leads tagués · "
            f"batch `{st.session_state[f'{key_prefix}_batch']}`"
        )
        st.download_button(
            f"⬇️ Télécharger {st.session_state[f'{key_prefix}_fname']}",
            st.session_state[f"{key_prefix}_csv"],
            st.session_state[f"{key_prefix}_fname"],
            "text/csv",
            key=f"{key_prefix}_dl_tagged",
        )


@st.dialog("⚠️ Confirmer l'export campagne", width="large")
def _confirm_export_dialog(
    *,
    pool: pd.DataFrame,
    top_n: pd.DataFrame,
    lead_ids: list,
    channel: str,
    csv_bytes: bytes,
    fname: str,
    key_prefix: str,
) -> None:
    """Modal récap + confirm/cancel. record_export only on confirm."""
    st.markdown(f"### Canal : **`{channel}`**")
    score_col = "score" if "score" in top_n.columns else None

    m1, m2, m3 = st.columns(3)
    m1.metric("Leads à tagger", len(lead_ids))
    m2.metric("Pool dispo", len(pool))
    if score_col:
        m3.metric(
            "Score min — max",
            f"{int(top_n[score_col].min())} — {int(top_n[score_col].max())}",
        )

    st.markdown("**Effet du tag :**")
    st.markdown(
        f"- Ces leads seront marqués `{channel}=exporté` (table `lead_exports`)\n"
        "- Exclus par défaut des futurs exports du même canal\n"
        "- Re-tag = écrasement (même lead × même canal = une seule ligne)\n"
        "- Aucun effet sur l'autre canal"
    )

    sample_cols = [c for c in ("prénom", "nom", "score", "entreprise") if c in top_n.columns]
    st.markdown("**🥇 Top 3 du batch :**")
    st.dataframe(top_n[sample_cols].head(3), use_container_width=True, hide_index=True)
    if len(top_n) > 3:
        st.markdown("**📉 Bottom 3 du batch :**")
        st.dataframe(top_n[sample_cols].tail(3), use_container_width=True, hide_index=True)

    st.divider()
    col_confirm, col_cancel = st.columns([1, 1])
    if col_confirm.button(
        "✅ Confirmer le tag",
        type="primary",
        key=f"{key_prefix}_confirm",
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
        key=f"{key_prefix}_cancel",
        use_container_width=True,
    ):
        st.rerun()
