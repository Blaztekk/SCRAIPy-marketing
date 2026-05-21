"""Guide — documentation interactive (expanders)."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.markdown("## 📖 Guide d'utilisation")
    st.caption("Ce dashboard permet d'explorer la base de contacts qualifiés et de l'exporter en CSV.")

    st.divider()

    with st.expander("🏠 Onglet Accueil", expanded=True):
        st.markdown("""
**Vue d'ensemble de la base.**

- Les **métriques du haut** donnent le nombre d'entreprises confirmées et de contacts selon leur statut.
- Le tableau **Élus CSE par entreprise** montre les 20 entreprises les mieux couvertes.

> *Conseil :* commencez toujours par l'Accueil pour avoir une idée de la volumétrie avant de filtrer.
""")

    with st.expander("🏢 Onglet Entreprises"):
        st.markdown("""
**Liste des entreprises du périmètre.**

| Colonne | Signification |
|---|---|
| `statut` | `confirmed` = entreprise validée dans le périmètre |
| `tranche_effectif` | Tranche INSEE (ex: `5001_10000` = 5 000 à 10 000 salariés) |
| `naf_code` | Code activité (ex: `35.11Z` = production d'électricité) |

**Filtres disponibles :** statut, code NAF, tranche effectif, recherche par nom ou SIREN.

**Mode ET / OU** : avec *ET* tous les filtres doivent correspondre ; avec *OU* un seul suffit.

Le bouton **⬇️ Export CSV entreprises** télécharge la liste filtrée.
""")

    with st.expander("👥 Onglet Contacts — sous-onglets"):
        st.markdown("""
L'onglet Contacts est divisé en trois vues :

| Sous-onglet | Usage |
|---|---|
| **🔍 Explorer** | Recherche avancée multi-critères, inspecteur de contact, export libre |
| **📧 Rdy mail** | Contacts avec email, triés par score — vue action pour campagnes email |
| **📞 Rdy call** | Contacts avec téléphone, triés par score — vue action pour appels |

#### Score composite (Rdy mail / Rdy call)

Chaque contact reçoit un score composite (max 34 pts hors bonus campagne) :

| Critère | Points |
|---|---|
| `cse_status = oui` | +10 |
| Rôle bureau (Secrétaire / Trésorier·e / Président) | +7 |
| Rôle titulaire / membre | +3 |
| Email présent | +5 |
| Téléphone présent | +3 |
| Téléphone mobile (06/07) | +2 |
| Nb sources (plafonné à 5) | +1 à +5 |
| Source datant de moins de 2 ans | +2 |

**Bonus campagne** (configurable dans Rdy mail) : +3 pts par syndicat cible et par entreprise cible.

> Un score élevé = contact prioritaire. Les commerciaux commencent par le haut du tableau.
""")

    with st.expander("👥 Onglet Contacts — Explorer — les filtres"):
        st.markdown("""
**Recherche en deux groupes combinables.**

#### Groupe 1 — Statuts CSE / Syndicat
Filtre sur le type de contact :

| Champ | Valeurs |
|---|---|
| `cse_status` | `oui` = élu·e au CSE · `inconnu` = statut non confirmé |
| `union_status` | `oui` = syndiqué·e confirmé·e |
| Instance CSE | `CSE` (établissement) · `CSEC` (central) |
| Syndicat | CFDT, CGT, FO, CFE-CGC… |

#### Groupe 2 — Coordonnées
Filtre sur la présence des données de contact : email, téléphone, nom.

#### Combiner les groupes
Le radio **"Combiner les groupes avec : ET / OU"** entre les deux blocs définit comment ils s'articulent.

**Exemples concrets :**

| Objectif | Réglage |
|---|---|
| Tous les élus CSE *ou* syndiqués | G1 : `cse=oui` + `union=oui`, mode G1 = **OU** |
| Élus CSE qu'on peut contacter | G1 : `cse=oui`, G2 : email ✓, inter = **ET** |
| N'importe qui avec email *ou* téléphone | G2 : email ✓ + phone ✓, mode G2 = **OU** |
| Élus CSE *ou* syndiqués avec coordonnées | G1 : `cse=oui`+`union=oui` mode **OU**, G2 : email ✓ mode **OU**, inter = **ET** |

#### Contexte (toujours ET)
- **SIREN entreprise** : restreindre à une entreprise précise
- **Nom / email contient** : recherche libre sur le nom ou l'adresse email
- **Min sources** : n'afficher que les contacts avec au moins N sources (plus fiable = plus élevé)
- **Source < X ans** : exclure les données trop anciennes (ex: 3 = sources de moins de 3 ans)
""")

    with st.expander("👥 Onglet Contacts — Explorer — l'inspecteur"):
        st.markdown("""
**Cliquer une ligne du tableau** ouvre l'inspecteur détaillé en bas de page.

Il affiche :
- **Coordonnées** complètes (email, téléphone, statuts CSE/Syndicat, mandat)
- **Entreprise** (nom, SIREN, niveau de confiance)
- **Sources** : chaque source ayant permis d'identifier ce contact

Pour chaque source, un **extrait du document original** est affiché avec le nom du contact surligné en jaune. Cela permet de vérifier le contexte (page web, PDF de résultats électoraux, etc.).

> *Conseil :* le nombre de sources (`nb_sources`) est un bon indicateur de fiabilité. Un contact avec 3+ sources est très probablement correct.
""")

    with st.expander("⬇️ Export CSV"):
        st.markdown("""
Le bouton **⬇️ Export CSV** télécharge tous les contacts correspondant aux filtres actifs (dans la limite d'affichage).

**Conseil avant d'exporter :**
1. Vérifiez les métriques (total filtres, avec email, avec téléphone) pour estimer la volumétrie
2. Si le total dépasse la limite d'affichage (500 par défaut), augmentez la **Limite résultats** dans le contexte

Le fichier CSV est encodé en UTF-8 et s'ouvre directement dans Excel ou Google Sheets.
""")

    with st.expander("🔄 Données & mise à jour"):
        st.markdown("""
- Les données sont **rafraîchies automatiquement toutes les 2 minutes**.
- Le bouton **🔄 Rafraîchir** en sidebar force un rechargement immédiat.
- La base est alimentée en continu par le pipeline SCRAIPy — de nouveaux contacts peuvent apparaître d'une session à l'autre.
- Accès **lecture seule** : aucune modification n'est possible depuis ce dashboard.
""")
