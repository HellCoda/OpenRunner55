# Plan de la Phase 4 — Développement

> Vue d'ensemble de la phase de développement. Complète `docs/cadrage/mvp.md`
> (ordre de construction suggéré) avec l'état réel et la séquence détaillée.
> Source de vérité pour le suivi d'avancement de la phase.

## Principes de séquence

1. **Backend avant frontend** pour chaque epic fonctionnel. Le backend fige
   le contrat (interfaces publiques), le frontend s'y appuie.
2. **UI intégrée par epic**, pas en bloc final. Chaque epic amène sa vue
   GTK au moment où son backend est validé. L'Epic 4 (historique + logs)
   reste un chantier transverse en fin de MVP.
3. **Un chantier actif à la fois** (Franck est goulot unique). Le chantier
   en préparation peut être briefé pendant que l'actif est en revue.
4. **Gate de validation** à chaque epic : tests verts + revue DP + merge
   sur `main` avant d'ouvrir le suivant.

## État d'avancement

| Epic | Périmètre | État | Branche | Commit de merge |
|------|-----------|------|---------|-----------------|
| 1 — Auth | Backend + UI login | ✅ Livré (session 1) | `feat/epic-1-auth` | `2a762a0` |
| 2 — Workouts Cloud → Montre | Backend | ✅ Livré | `feat/epic-2-workouts` | `bd68650` |
| 2 — Workouts Cloud → Montre | UI (liste, sélection, envoi) | ✅ Livré | `feat/epic-2-frontend` | `221002b` |
| 3 — Activités Montre → Cloud | Backend | ✅ Livré | `feat/epic-3-activities` | `b87e3d5` |
| 3 — Activités Montre → Cloud | UI (liste, sélection, envoi) | ✅ Livré | `feat/epic-3-frontend` | `f91a7ff` |
| 4 — Historique & logs | UI transverse | ⏳ Prochain chantier | — | — |
| 5 — Robustesse | Retry 429, déconnexion USB, etc. | ⏳ Post-MVP (Should) | — | — |

## Séquence détaillée

### Étape 1 — Epic 1 (Auth) ✅

- Backend : `auth/`, `garmin/client.py`, `store/database.py`, `store/logger.py`
- UI : `ui/auth_view.py` (écran de login GTK4)
- Merge : `2a762a0` sur `main`

### Étape 2 — Epic 2 backend ✅

- `watch/detector.py`, `watch/filesystem.py`, `store/transfers.py`,
  `store/history.py`, `garmin/client.py` (extension), `sync/workouts.py`
- Contrat figé : `push_workouts(items: list[WorkoutSummary])`,
  `WorkoutSummary.date: datetime | None`, chemins `WatchFilesystem`
  relatifs à `GARMIN/`, `WatchDetector.start()/stop()`.
- Merge : `bd68650` sur `main`

### Étape 3 — Epic 2 frontend ✅

- `ui/app.py` (shell post-auth, navigation 3 sections, barre bleue Garmin),
  `ui/watch_view.py` (zone GC workouts + zone Montre placeholder),
  `ui/workouts_controller.py` (logique de présentation sans GTK)
- Fix backend livré au passage : `check_same_thread=False` dans
  `store/database.py` (bug E3 — écritures SQLite cross-thread du worker
  `push_workouts` levaient `ProgrammingError`, base restait vide). ADR-005
  révisée. Test de non-régression `test_database_cross_thread.py`.
- Validation runtime : envoi réel de workouts vers la FR55, base SQLite
  peuplée (`transferred_files`, `sync_history`, `operation_logs`).
- Merge : `221002b` (frontend) + `8957b98` (fix SQLite) sur `main`

### Étape 4 — Epic 3 (Montre → Cloud) ✅

- Backend ✅ : `sync/activities.py` (`list_uploadable_files`,
  `push_activities`), `garmin/client.upload_activity`,
  `watch/filesystem.absolute_path/file_size`. Contrats figés et validés en
  réel. Merge `b87e3d5`.
- Frontend ✅ : `ui/activities_controller.py` (logique de présentation,
  pattern `WorkoutsController`), extension `ui/watch_view.py` (zone Montre
  fonctionnelle : liste, sélection, bouton « Synchroniser vers GC », barre
  de progression, résumé). Brief : `docs/dev/Epic-3-brief-frontend.md`.
  Notes : `docs/dev/Epic-3-notes-frontend.md`.
- Décision UX : pré-sélection des fichiers `already_transferred=False`,
  bouton « Tout sélectionner », skip natif côté backend.
- Validation réelle : FR55, 234 fichiers référencés, 213 synchronisés.
  Cycle complet OK. 2 bugs corrigés pendant la revue DP (ordre
  `_on_push_failure`, résumé borné dans ScrolledWindow).
- Merge : `f91a7ff` sur `main`.
- Points reportés vers Epic 4 : 409 → skip, retry 5xx, granularité
  historique, cosmétique paneaux/bandeau (cf. `Epic-3-notes-frontend.md`).

### Étape 5 — Epic 4 (Historique & logs)

- UI : vue historique (`SyncHistoryStore.get_history`), vue logs
  (`operation_logs` via `store/logger.py` en lecture).
- Dépendances : `store/history.py` (existant), `store/logger.py` (existant).
- Backend : quasi-néant (les stores existent depuis Epic 1/2). Ajout
  éventuel d'une méthode de lecture publique si manquante.
- Gate : tests + revue DP + merge.

### Étape 6 — MVP validation

- Condition de validation MVP (cf. `docs/cadrage/mvp.md`) : un workout
  créé sur GC est sélectionné, poussé sur le FR55 via USB, et une activité
  enregistrée sur la montre est remontée avec succès sur GC — le tout
  depuis l'interface GTK.
- Tests d'acceptance sur montre réelle + compte GC réel (jalons E2).

### Étape 7 — Epic 5 (Robustesse, post-MVP)

- Should : retry 429 avec backoff visible (US-5.1), détection déconnexion
  USB en cours de transfert (US-5.2).
- Could : reconnexion auto après expiration session (US-5.2),
  notifications desktop (US-5.3).
- Pas dans le périmètre MVP — à planifier après validation MVP.

## Jalons

| Jalon | Description | État |
|-------|-------------|------|
| E1 | Epic 1 livré (auth + UI login) | ✅ |
| E2 | Epic 2 backend livré | ✅ |
| E3 | Epic 2 frontend livré (MVP Cloud → Montre complet) | ✅ |
| E4 | Epic 3 livré (MVP Montre → Cloud complet) | ✅ |
| E5 | Epic 4 livré (historique + logs) | ⏳ |
| E6 | MVP validé (condition `docs/cadrage/mvp.md`) | ⏳ |
| E7 | Epic 5 (robustesse, post-MVP) | ⏳ |

## Dette technique suivie

- Index unique `(file_name, direction, source)` sur `transferred_files`
  + `INSERT OR IGNORE` dans `mark_transferred`.
- Désinscription callback `WatchDetector.on_status_changed`.
- Garde `WatchFilesystem._resolve` sur chemin relatif.
- Officialisation de l'écart ADR-006 (déclencheur sur label `GARMIN`).
- Pagination `fetch_workouts` si > 20 workouts côté UI.
- Granularité de l'historique : `push_workouts`/`push_activities` appelé par
  fichier par le controller → N entrées `sync_history` « 1/1 » au lieu d'une
  agrégée « X/Y ». À trancher pour l'Epic 4 (affecte l'affichage UX §4.2).
- **409 « Duplicate Activity » traité comme échec** au lieu de skip côté
  backend (`push_activities` catch générique). Constaté en validation réelle
  Epic 3 (200/213 fichiers marqués échoués alors que sur GC). Gain d'UX
  majeur pour peu d'effort — priorité haute pour Epic 4.
- **Retry 5xx non couvert** (ADR-007 couvre 429 seulement). Cloudflare 520
  transitoire constaté en validation réelle. Étendre le retry/backoff aux
  5xx (`retryable: true` dans la réponse Garmin).
- **Cosmétique UI** : curseurs `Gtk.Paned` entre zones, placement du bandeau
  « montre connecté ». Transverse, hérité Epic 2.

---

*Directeur de Projet — Plan phase 4. Document vivant, mis à jour à chaque
gate d'epic.*
