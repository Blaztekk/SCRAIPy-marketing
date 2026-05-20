# SCRAIPy — Marketing Dashboard

Dashboard read-only pour explorer les contacts qualifiés (élus CSE, syndiqués).
Déployé sur [Streamlit Community Cloud](https://share.streamlit.io).

## Ce que c'est

- Filtres groupés ET/OU sur statuts CSE/Syndicat et coordonnées
- Export CSV des contacts filtrés
- Accès lecture seule (user `scraipy_marketing` sur Neon)

## Mettre à jour le dashboard

Ce fichier est une **copie** — la source de vérité est dans le repo privé `SCRAIPy`.

```
# 1. Modifier dashboard_marketing.py dans SCRAIPy, puis :
copy "d:\Projets\SCRAIPy\dashboard_marketing.py" "d:\Projets\SCRAIPy-marketing\dashboard_marketing.py"

# 2. Commiter + pusher
cd d:\Projets\SCRAIPy-marketing
git add dashboard_marketing.py
git commit -m "update: dashboard marketing"
git push
```

Streamlit Cloud redéploie automatiquement (~1 min après le push).

## Config Streamlit Cloud

App settings > Secrets :
```toml
DATABASE_URL = "postgresql+psycopg://scraipy_marketing:MOT_DE_PASSE@ep-aged-hall-aluqq93n-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
```
