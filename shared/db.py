"""DB connection + query helpers shared between internal and marketing dashboards.

Loads DATABASE_URL from st.secrets first (Streamlit Cloud), then falls back to .env.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@st.cache_resource
def get_engine() -> Engine:
    url = None
    try:
        url = st.secrets.get("DATABASE_URL")
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        pass
    url = url or os.getenv("DATABASE_URL")
    if not url:
        st.error("DATABASE_URL manquant (secrets Streamlit ou .env)")
        st.stop()
    return create_engine(url, pool_pre_ping=True, pool_recycle=280)


def _engine() -> Engine:
    return get_engine()


def make_cached_query(ttl: int = 60):
    """Build a cached_query function with a configurable TTL.

    Used because @st.cache_data must be applied at module top-level with a fixed
    TTL — different dashboards want different freshness (60s internal, 120s public).
    """
    @st.cache_data(ttl=ttl)
    def cached_query(sql: str, params: dict | None = None) -> pd.DataFrame:
        with _engine().connect() as conn:
            return pd.read_sql_query(text(sql), conn, params=params or {})
    return cached_query


def query(sql: str, **params) -> pd.DataFrame:
    """Run an uncached query. Use for one-shot fetches with parameters."""
    with _engine().connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def scalar(sql: str, **params):
    """Run an uncached query returning a single scalar. Returns 0 on None."""
    with _engine().connect() as conn:
        return conn.execute(text(sql), params).scalar() or 0
