# Brief de mission — Epic 5 : Sync auto & UX quotidienne

Tu es le Developer du projet OpenRunner55. Voici ta mission pour l'Epic 5.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epics 1 à 4 livrés et mergés sur `main`** (248 tests verts). L'auth, la
sync bidirectionnelle (workouts GC → montre, activités montre → GC),
l'historique et les logs sont fonctionnels et validés en réel sur FR55.

L'Epic 5 corrige les points remontés lors des tests réels du 21/09/2026
(cf. `docs/dev/backlog-post-epic-4.md`) et ajoute la sync automatique au
branchement de la montre — le cœur du cas d'usage quotidien.

## Décisions de cadrage (DP — figées)

| Sujet | Décision |
|-------|----------|
| Sync auto — déclencheur | Connexion USB + app déjà ouverte. Pas de service système. |
| Sync auto — sens | Montante seule (activités → GC). La descendante (workouts) nécessite sélection, pas d'auto. |
| Sync auto — feedback | Réutiliser la barre de progression existante d'`ActivitiesController`. |
| Sync auto — conflit | Si sync manuelle en cours, l'auto est ignorée (pas de file d'attente). |
| Grisement | Masquer par défaut les `already_transferred=True`. Bouton « Afficher tout » pour les revoir en grisé. Identique workouts/activités. |
| Refresh | Bouton « ↻ » sur chaque liste. Refresh auto de la liste montre après une sync réussie. Pas de refresh au focus fenêtre. |
| 409 Duplicate | Catch spécifique dans `push_activities` → `skipped += 1` + `transfers.mark_transferred`. |

## Périmètre (4 chantiers)

### Chantier 1 — 409 Duplicate Activity → skip (backend)

**Problème** : `push_activities` (`sync/activities.py`) catche le 409
« Duplicate Activity » de Garmin Connect dans le `except Exception`
générique → compté comme `failed` + message d'erreur affiché. Sur 213
fichiers avec store SQLite vide (première utilisation), 200 ont été marqués
échoués alors que les données sont bien sur GC.

**Sémantique** : un 409 signifie que GC a déjà le fichier. C'est un skip,
pas un échec. GC a confirmé la présence — on peut marquer le fichier comme
transféré dans `transferred_files`.

**À implémenter** dans `sync/activities.py` → `push_activities` :

1. Avant le `except Exception` générique, catcher spécifiquement l'exception
   correspondant au 409 Duplicate. Le dev doit identifier quelle exception
   exacte la lib `garminconnect` lève pour un 409 (probablement
   `GarminConnectConnectionError` avec un message contenant "409" ou
   "duplicate" — à vérifier dans le code de la lib et/ou par inspection du
   message d'erreur observé en validation réelle).
2. Sur 409 : `skipped += 1` +
   `transfers.mark_transferred(item.path.name, _DIRECTION, item.category)` +
   `logger.log("sync.activities", "info", "Activity déjà présente sur GC :
   {item.path}")`. **Aucune entrée dans `errors`**.
3. Le `except Exception` générique reste pour les autres erreurs.

**Tests** (`tests/unit/test_sync_activities.py`) :

- `test_409_treated_as_skip` : un fichier qui lève l'exception 409 →
  `skipped == 1`, `failed == 0`, `errors == []`, fichier marqué transféré.
- `test_409_mixed_with_success` : 1 fichier 409 + 1 fichier OK →
  `skipped == 1`, `success == 1`, `failed == 0`.
- `test_409_mixed_with_real_failure` : 1 fichier 409 + 1 fichier OSError →
  `skipped == 1`, `failed == 1`.
- `test_non_409_connection_error_still_failed` : une
  `GarminConnectConnectionError` dont le message ne contient pas "409"/
  "duplicate" → toujours `failed`, pas de skip (garde-fou).

**Contrainte** : la détection du 409 doit être robuste — ne pas skipper
des erreurs légitimes. Si la lib lève une exception spécifique, l'utiliser ;
sinon, matcher sur le message (insensible à la casse, recherche "409" ou
"duplicate"). Documenter le choix dans les notes de dev.

### Chantier 2 — Refresh des listes (frontend)

**Problème** : aucune liste ne peut être rafraîchie manuellement. Le
listing des fichiers de la montre ne se déclenche qu'au branchement USB ou
à la construction de la vue. Le listing des workouts GC ne se déclenche
qu'à la construction. Pour voir les nouvelles activités ou les nouveaux
workouts, il faut fermer/rouvrir l'app.

**À implémenter** :

1. **`WorkoutsController`** : exposer une méthode `refresh_workouts()`
   qui relance `fetch_workouts_async` (équivalent à un re-chargement). La
   vue connecte un bouton « ↻ » à cette méthode.
2. **`ActivitiesController`** : exposer une méthode `refresh_files()`
   qui relance `list_uploadable_files_async` (si la montre est connectée).
   La vue connecte un bouton « ↻ » à cette méthode.
3. **Refresh auto après sync** : après un `push_activities_async` réussi
   (au moins un fichier envoyé), relancer automatiquement le listing des
   fichiers de la montre. Objectif : refléter immédiatement l'état
   `already_transferred` mis à jour.
4. **`WatchView`** : ajouter un bouton « ↻ » dans l'en-tête de chaque
   zone (GC workouts + fichiers montre). Style `flat`, icône
   `view-refresh-symbolic`. Inactif pendant `is_loading` / `is_sending`.

**Tests** :

- `WorkoutsController.refresh_workouts` relance `fetch_workouts_async`
  (vérifier que le worker est lancé).
- `ActivitiesController.refresh_files` relance `list_uploadable_files_async`
  si montre connectée ; noop si déconnectée.
- `ActivitiesController` : après `push_activities_async` réussi avec
  `success > 0`, `list_uploadable_files_async` est relancé
  automatiquement (vérifier via un mock/spy).
- Après `push_activities_async` avec `success == 0` (tout échoué), pas de
  refresh auto.

### Chantier 3 — Grisement fichiers déjà transférés (frontend)

**Problème** : à chaque sync, l'app propose plus de 200 fichiers déjà
transférés. Franck veut qu'ils soient masqués par défaut.

**À implémenter** :

1. **`ActivitiesController`** : ajouter un flag `hide_transferred: bool`
   (défaut `True`). Quand `True`, la propriété `files` ne retourne que les
   fichiers `already_transferred=False`. Exposer `set_hide_transferred(bool)`
   qui notifie la vue.
2. **`WorkoutsController`** : pas concerné (les workouts ne sont pas
   marqués `already_transferred` de la même façon — ils sont décochés
   après envoi). **Scope limité à la zone Montre (activités).**
3. **`WatchView`** : un `Gtk.ToggleButton` « Masquer transférés » (actif
   par défaut) dans l'en-tête de la zone Montre. Quand désactivé, la liste
   affiche tous les fichiers (les transférés en grisé, non sélectionnables
   par défaut).
4. **Compteur** : afficher « N nouveaux · M déjà transférés » dans
   l'en-tête quand `hide_transferred=True`, pour que l'utilisateur sache
   qu'il y a des fichiers masqués.

**Tests** :

- `hide_transferred=True` par défaut : `files` ne retourne que les non
  transférés.
- `set_hide_transferred(False)` : `files` retourne tous les fichiers.
- `selected_count` ne compte que les fichiers visibles (un fichier masqué
  ne peut pas être dans la sélection).
- Le toggle notifie la vue (`on_files_changed`).

### Chantier 4 — Sync auto au branchement (backend + frontend)

**Problème** : Franck branche sa montre, s'attend à ce qu'une sync se
déclenche. Rien ne se passe — il doit déclencher manuellement.

**À implémenter** :

1. **`ActivitiesController.on_watch_status_changed(True)`** : après le
   listing réussi des fichiers, si `hide_transferred=True` et qu'il y a
   des fichiers non transférés, déclencher automatiquement
   `push_activities_async` sur ces fichiers (sélection automatique des
   nouveaux, puis envoi).
2. **Garde-fous** :
   - Si `is_sending` est déjà `True` (sync manuelle en cours), ne pas
     déclencher l'auto.
   - Si aucun fichier non transféré, ne rien faire (pas de sync inutile).
   - L'auto-sync ne se déclenche qu'une fois par branchement (flag
     `_auto_sync_done` réinitialisé au débranchement).
3. **Feedback** : la barre de progression existante reflète la sync auto
   comme une sync manuelle. Pas de distinction visuelle — l'utilisateur
   voit sa sync progresser.
4. **Log** : logger `"sync.activities", "info", "Sync auto déclenchée au
   branchement (N nouveaux fichiers)"` au démarrage de l'auto.

**Tests** :

- Branchement avec 3 nouveaux fichiers → `push_activities_async` lancé
  automatiquement, sélection = les 3 fichiers.
- Branchement avec 0 nouveau fichier → pas d'auto-sync.
- Sync manuelle en cours au branchement → pas d'auto-sync.
- Re-branchement après débranchement → l'auto-sync peut se redéclencher
  (flag réinitialisé).
- `_auto_sync_done` empêche un double déclenchement sur le même
  branchement.

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- L'UI appelle uniquement les Services (`sync/`). Jamais `store/`
  directement.
- L'UI n'importe jamais `garminconnect` directement.
- Les controllers ne contiennent aucune logique GTK (pas d'import
  `gi.repository`).
- Les dépendances Core sont injectées (duck-typing), types sous
  `TYPE_CHECKING` uniquement.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (248 existants + nouveaux).

## Critères de done

- Chantier 1 : 409 catché spécifiquement → skip + mark_transferred. Tests
  dédiés.
- Chantier 2 : boutons « ↻ » sur les deux listes + refresh auto après sync
  montre. Tests dédiés.
- Chantier 3 : `hide_transferred` dans ActivitiesController + toggle dans
  la vue + compteur. Tests dédiés.
- Chantier 4 : sync auto au branchement avec garde-fous. Tests dédiés.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.ui.app` ne lève pas.
- Aucun TODO non résolu dans le code livré.

## Ordre de construction — étapes avec validation

Chaque chantier = un checkpoint. Tests verts + commit + validation du
Directeur de Projet avant de passer au suivant.

| Étape | Chantier | Fichiers principaux |
|-------|----------|---------------------|
| **1** | 409 → skip | `sync/activities.py`, `tests/unit/test_sync_activities.py` |
| **2** | Refresh listes | `ui/workouts_controller.py`, `ui/activities_controller.py`, `ui/watch_view.py` |
| **3** | Grisement | `ui/activities_controller.py`, `ui/watch_view.py` |
| **4** | Sync auto | `ui/activities_controller.py` |

## Branche

`feat/epic-5-sync-auto`. Commits fréquents avec messages conventionnels
(`feat:`, `fix:`, `test:`, `chore:`). Un commit par chantier minimum.

## Références dans le repo

- `docs/dev/backlog-post-epic-4.md` — origine des items
- `docs/dev/Epic-3-notes-frontend.md` § Points à trancher — origine du 409
- `docs/decisions/adr-002.md` — architecture 3 couches
- `docs/decisions/adr-007.md` — retry/backoff
- `docs/decisions/adr-008.md` — stratégie de tests
- `src/openrunner55/sync/activities.py` — service à modifier (chantier 1)
- `src/openrunner55/garmin/client.py` — wrapper Garmin (exceptions)
- `src/openrunner55/ui/activities_controller.py` — controller à étendre
- `src/openrunner55/ui/workouts_controller.py` — controller à étendre
- `src/openrunner55/ui/watch_view.py` — vue à étendre
- `tests/unit/test_sync_activities.py` — tests du service (pattern)
- `tests/unit/test_activities_controller.py` — tests du controller (pattern)
- `docs/branching-rules.md` — règles de branches
