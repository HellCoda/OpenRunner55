# Contexte — OpenRunner55

- **Dernière mise à jour** : 2026-09-16
- **Phase** : 4 Développement — Epic 3 backend livré, brief frontend produit, prêt à démarrer le dev frontend

## Vision

Application desktop Linux (Fedora 44 / GNOME) pour synchroniser bidirectionnellement Garmin Connect et une montre Forerunner 55 via USB, sans Windows ni smartphone. Usage personnel, publication open-source prévue.

## Stack

- **Langage** : Python 3.12+
- **UI** : GTK 4 + libadwaita (ADR-003)
- **API Garmin** : `garminconnect` (headless, validé spike S-2)
- **Stockage** : SQLite (historique, logs, déduplication), GNOME Keyring (credentials)
- **USB** : pyudev + polling (ADR-006)
- **FIT** : `garmin-fit-sdk`
- **Packaging** : AppImage (ADR-009)

## Architecture

3 couches — UI → Services → Core. 7 packages, 10 modules. Détail : `docs/decisions/adr-002.md`.

```
src/openrunner55/
├── auth/        # Core — login, tokenstore, keyring
├── garmin/      # Core — wrapper API GC, retry, re-login 401
├── watch/       # Core — détection USB, lecture/écriture FIT
├── fit/         # Core — décodage, classification FIT
├── store/       # Core — SQLite (history, logs, transfers)
├── sync/        # Services — workouts, activities, wellness, history
└── ui/          # UI — auth_view, watch_view, history_view, account_view
```

## Décisions structurantes

| ADR | Sujet |
|-----|-------|
| ADR-001 | `garminconnect` validé |
| ADR-002 | Architecture 3 couches, `auth/` en Core |
| ADR-003 | GTK 4 + libadwaita |
| ADR-004 | GNOME Keyring, MFA non supporté (risque accepté) |
| ADR-005 | SQLite + `transferred_files` |
| ADR-006 | pyudev + polling |
| ADR-007 | Retry/backoff, délai 3s configurable |
| ADR-008 | Stratégie de tests |
| ADR-009 | Packaging AppImage |

## Périmètre MVP

10 user stories Must, ~7 jours/homme. Condition de validation : un workout créé sur GC est poussé sur la FR55 via USB, et une activité enregistrée sur la montre est remontée sur GC — depuis l'interface GTK. Détail : `docs/cadrage/mvp.md`.

## Prochaine action

**Epic 3 — Activités Montre → Cloud (frontend)** : dev de la zone Montre dans
`ui/watch_view.py` (liste `list_uploadable_files`, bouton « Synchroniser vers
GC » appelant `push_activities` dans un thread worker). Brief de mission
frontend produit : `docs/dev/Epic-3-brief-frontend.md`. Contrats backend figés
et validés en réel (smoke montre FR55 + upload GC).

**Décision UX tranchée (première sync)** : le backend fournit déjà le drapeau
`already_transferred` sur chaque `UploadableFile`. L'UI pré-sélectionne les
fichiers nouveaux (`already_transferred=False`), affiche le statut par ligne,
et propose un bouton « Tout sélectionner ». Les fichiers déjà transférés sont
skippés par `push_activities` sans appel API. Cas limite (store vide) accepté :
GC fait la déduplication côté serveur.

## Navigation par phase

- Phase 1 Découverte → `docs/decouverte/context.md`
- Phase 2 Cadrage → `docs/cadrage/context.md`
- Exploration (spikes) → `docs/exploration/context.md`
- Décisions (ADR) → `docs/decisions/context.md`
- Phase 3 Conception → `docs/conception/context.md`
