"""SQL WHERE-clause builders for ET/OU filter groups."""

from __future__ import annotations


def build_group(conds: list[str], mode: str) -> str | None:
    """Parenthesise a list of conditions joined by AND/OR (mode='ET'/'OU').

    Returns None if conds is empty so callers can filter it out.
    """
    if not conds:
        return None
    op = " AND " if mode == "ET" else " OR "
    return "(" + op.join(conds) + ")"


def build_where(fixed: list[str], dynamic: list[str], mode: str) -> list[str]:
    """Join fixed conditions (always AND) with a dynamic group (AND/OR by mode)."""
    if not dynamic:
        return fixed
    op = " AND " if mode == "ET" else " OR "
    return fixed + ["(" + op.join(dynamic) + ")"]
