"""Shared constants — loaded from scraipy core when available, fallback otherwise."""

from __future__ import annotations

try:
    from scraipy.projects.scope0.resolve import _AUTO_PROMOTE_ROLES as _ROLES_SET
    ROLES_OF_INTEREST: list[str] = sorted(_ROLES_SET)
except Exception:
    ROLES_OF_INTEREST = [
        "DS", "DSC", "Délégué Syndical Central",
        "Élu Suppléant CSE", "Élu Titulaire CSE",
        "Élue Suppléante CSE", "Élue Titulaire CSE",
        "Rapporteur", "Référent harcèlement",
        "Secrétaire", "Secrétaire CSE", "Secrétaire CSEC",
        "Secrétaire adjoint", "Secrétaire de CSE", "Secrétaire du CSE",
        "Trésorier", "Trésorière",
    ]
