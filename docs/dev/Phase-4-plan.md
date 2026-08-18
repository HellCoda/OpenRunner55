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
| 2 — Workouts Cloud → Montre | UI (liste, sélection, envoi) | 🔄 Prochain chantier | — | — |
| 3 — Activités Montre → Cloud | Backend + UI | ⏳ En attente | — | — |
| 4 — Historique & logs | UI transverse | ⏳ En attente | — | — |
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

### Étape 3 — Epic 2 frontend 🔄 (prochain)

- Brief à rédiger : `docs/dev/Epic-2-brief-frontend.md`
- Périmètre : `ui/app.py` (shell principal post-auth), `ui/watch_view.py`
  (liste des workouts GC, sélection multiple, détection USB, envoi)
- Dépendances : contrats backend Epic 2 (figés), `WatchDetector`,
  `fetch_workouts`/`push_workouts`, `SyncHistoryStore` (lecture).
- Points d'attention contrat :
  - `WatchDetector.start()` à appeler post-auth, `stop()` à la fermeture
  - `WorkoutSummary.date` peut être `None` (affichage à gérer)
  - Limite 20 workouts dans `fetch_workouts` (pagination à prévoir si > 20)
  - `push_workouts` ne skippe pas les déjà-transférés (la dédup locale
    n'est pas consultée dans le flux push — US-2.2 est en Should)
- Gate : tests UI (GTK mocké si possible) + revue DP + merge.

### Étape 4 — Epic 3 (Montre → Cloud)

- Backend : extension `sync/` (service `sync/activities.py` ou similaire),
  lecture `WatchFilesystem.list_fit_files` sur `Activity/`/`Monitor/`/
  `Sleep/`/`Metrics/`, upload via `garmin/client.py` (méthode à ajouter).
- UI : vue « Fichiers de la montre » + bouton « Synchroniser vers GC ».
- Dépendances : `watch/filesystem.py` (existant), `garmin/client.py`
  (à étendre), `store/transfers.py` (direction `"up"`).
- Point ouvert : filtre des fichiers `.FIT` acceptés par GC (US-3.3,
  Should) — découverte empirique en tests. Démarrer en remontée brute,
  affiner ensuite.
- Gate : tests + revue DP + merge.

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
| E3 | Epic 2 frontend livré (MVP Cloud → Montre complet) | ⏳ |
| E4 | Epic 3 livré (MVP Montre → Cloud complet) | ⏳ |
| E5 | Epic 4 livré (historique + logs) | ⏳ |
| E6 | MVP validé (condition `docs/cadrage/mvp.md`) | ⏳ |
| E7 | Epic 5 (robustesse, post-MVP) | ⏳ |

## Dette technique suivie (post-Epic 2 backend)

- Index unique `(file_name, direction, source)` sur `transferred_files`
  + `INSERT OR IGNORE` dans `mark_transferred`.
- Désinscription callback `WatchDetector.on_status_changed`.
- Garde `WatchFilesystem._resolve` sur chemin relatif.
- Officialisation de l'écart ADR-006 (déclencheur sur label `GARMIN`).
- Pagination `fetch_workouts` si > 20 workouts côté UI.

---

*Directeur de Projet — Plan phase 4. Document vivant, mis à jour à chaque
gate d'epic.*
