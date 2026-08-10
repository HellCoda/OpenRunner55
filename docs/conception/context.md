# Contexte — Phase 3 Conception

- **État** : terminée, gate validée (2026-08-09)
- **Livrable principal** : `ux-design.md`

## Contenu

- `ux-design.md` — parcours utilisateurs (A à F), architecture d'information, wireframes, design system, critères d'acceptance par epic. Référence pour l'Epic 4 (UI).
- `rapport-supervision-conception.md` — revue d'alignement ADR-002 à 007 vs amont (08/08). Points M1/M3/C1/C5/C6 identifiés puis résolus.
- `brief-architecte-backend-alignement-ux.md` — 4 corrections architecture appliquées (slugify, `account_view`, pas d'API update, pont `sync/history.py`).
- `brief-ux-designer-alignement-backend.md` — 5 corrections UX appliquées (pont `sync/history.py`, retrait parcours suppression, slug, `account_view`, retrait boutons modifier).

## Décisions produit issues de la conception

- Nommage workouts : `{slug(nom)}.FIT` (lisible USB, FAT32-compatible).
- Suppression d'activités depuis l'app : hors MVP (backlog).
- Changement credentials : déconnexion + reconnexion (pas d'API update).
- MFA : non supportée, message clair si détectée.

## Sortie de phase

Conception verrouillée. Toutes les exigences couvertes, toutes les incohérences résolues. Prêt pour Phase 4 Développement (Epic 1 Auth en premier).
