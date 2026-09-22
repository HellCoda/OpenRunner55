# Notes de dev — Epic 5 : Sync auto & UX quotidienne

> Document vivant. Consigne les choix, écarts et observations des developers
> au fil des 4 chantiers de l'Epic 5. Complète le brief (`Epic-5-brief.md`)
> sans le dupliquer. Source de vérité pour la revue du Directeur de Projet.
>
> Branche : `feat/epic-5-sync-auto`.

## Baseline

- **Tests au départ** : 273 verts (`pytest tests/ -m unit`) — Epic 4 mergé.
- **Python / libadwaita** : 3.14.7 / 1.9.3 (inchangé).

---

## Chantier 1 — 409 Duplicate Activity → skip (commit `da397bf`)

**Livrables** : `sync/activities.py` modifié (helper `_is_duplicate_409` +
branche `except GarminConnectConnectionError`), 4 tests dans
`test_sync_activities.py`. Régression : 277 verts.

### Choix

1. **Détection du 409 par match de message** : la lib `garminconnect` ne
   fournit pas d'exception dédiée pour le 409 (uniquement 401, 429, 404).
   `upload_activity` propage un `GarminConnectConnectionError("API Error
   409 - ...")`. On catche `GarminConnectConnectionError` spécifiquement
   (pas `Exception`) et on matche le message insensible à la casse sur
   `"409"` ou `"duplicate"` (ce dernier couvre le chemin `import_activity`
   et une éventuelle évolution de la lib).

2. **Skip sémantique** : sur 409, `skipped += 1` +
   `transfers.mark_transferred(...)` + log info. **Aucune entrée dans
   `errors`**. GC a confirmé la présence — on marque le fichier comme
   transféré.

3. **Garde-fou** : une `GarminConnectConnectionError` dont le message ne
   contient pas "409"/"duplicate" reste traitée comme un échec (test
   `test_non_409_connection_error_still_failed`).

### Dette technique

**Import direct `garminconnect` dans `sync/activities.py`** : ADR-002
l'autorise côté Service, mais un couplage plus propre serait de faire
remonter une exception domaine (`DuplicateActivityError`) depuis le
wrapper `garmin/client.py`. Noté pour un chantier ultérieur — pas
bloquant.

---

## Chantier 2 — Refresh des listes (commit `aa559c2`)

**Livrables** : `refresh_workouts()` + `refresh_files()` + refresh auto
après sync + boutons « ↻ » dans `WatchView`. 6 tests. Régression : 283
verts.

### Choix

1. **`refresh_workouts()` = méthode dédiée** (alias sémantique de
   `fetch_workouts_async`) : la vue exprime l'intention utilisateur
   (« refresh ») plutôt que l'opération technique (« fetch »). Coût
   minimal, aucune duplication.

2. **`refresh_files()` réutilise les callbacks mémorisés** :
   `self.list_uploadable_files_async(self._list_on_done,
   self._list_on_error)`. Noop si montre déconnectée ou chargement en
   cours (garde existante).

3. **Refresh auto après sync** dans `_on_push_success` : si
   `result.success > 0`, relance `list_uploadable_files_async`. Le
   re-listing garantit que l'état SQLite est la vérité et rafraîchit la
   liste complète. La garde anti-re-entrante couvre le cas d'un
   chargement déjà en cours.

4. **Boutons « ↻ »** : `Gtk.Button` avec icône `view-refresh-symbolic`,
   style `flat`, dans l'en-tête de chaque zone. Inactif pendant
   `is_loading` / `is_sending` (et si montre déconnectée pour la zone
   Montre).

### Écarts / ajustements

- **Tests `TestPush` existants impactés** par le refresh auto : le
  re-listing vidait l'état manuel. Ajusté le helper `_controller` pour
  que le `FakeWatch` retourne les mêmes fichiers que l'état manuel.
  Pré-marquage de `skip.fit` dans `FakeTransfers` pour aligner le store
  avec le drapeau `already_transferred=True`.

---

## Chantier 3 — Grisement fichiers déjà transférés (commit `1aa3c84`)

**Livrables** : `hide_transferred` (défaut `True`) + `new_count` +
`transferred_count` + `set_hide_transferred()` + toggle + compteur. 9
tests. Régression : 292 verts.

### Choix

1. **Masquer par défaut** (`hide_transferred=True`) : la propriété
   `files` filtre les `already_transferred=True`. Le toggle permet de
   les réafficher en grisé.

2. **`select_all()` respecte le filtre** : ne sélectionne que les
   fichiers visibles. `select_new_only()` inchangé (déjà compatible).

3. **Sélection nettoyée au masquage** : `set_hide_transferred(True)`
   retire de la sélection tout chemin masqué (un fichier invisible ne
   peut pas rester sélectionné).

4. **Compteur** : « N nouveaux · M déjà transférés » dans le sous-titre
   quand `hide_transferred=True` et `transferred_count > 0`. Sinon
   « Fichiers (N) » (comportement inchangé).

5. **Toggle visible mais grisé** quand `transferred_count == 0` :
   l'utilisateur voit la fonctionnalité même sur une liste sans
   transféré.

### Écarts / ajustements

- **3 tests existants adaptés** : `select_all()` ne sélectionne plus
  les transférés par défaut. Tests ajustés avec `set_hide_transferred
  (False)` explicite avant `select_all()` quand l'intention est de
  sélectionner tout y compris les transférés. `test_select_all_includes
  _transferred` renommé `test_select_all_includes_transferred_when_shown`.

---

## Chantier 4 — Sync auto au branchement (commit `dd73714`)

**Livrables** : flag `_auto_sync_done` + déclenchement dans
`_on_list_success` + reset au débranchement. 6 tests. Régression : 298
verts.

### Choix

1. **Flag `_auto_sync_done`** : `False` à la construction, reset à
   `False` au débranchement (`on_watch_status_changed(False)`), set à
   `True` au premier listing réussi post-branchement — qu'une auto-sync
   soit déclenchée ou non (même si 0 nouveaux fichiers, on ne retry
   pas).

2. **Déclenchement dans `_on_list_success`** : après la pré-sélection
   des nouveaux fichiers, si `not _auto_sync_done` et `new_count > 0`
   et `not is_sending` → log info + `push_activities_async` avec
   callbacks noop. Le flag est set **avant** le déclenchement pour
   éviter un double déclenchement via le refresh auto (chantier 2).

3. **Comportement à l'ouverture** : si la montre est déjà branchée à
   l'ouverture de l'app, le listing de construction déclenche
   l'auto-sync. Accepté — cohérent avec le cas d'usage « je branche,
   j'ouvre, ça sync ».

4. **Approche de test : mock de `push_activities_async`** : override
   sur l'instance par un spy qui enregistre les appels sans lancer de
   thread. Déterminisme total, pas de condition de course. Les tests
   `TestSyncAuto` valident la *décision* de déclenchement (garde-fous),
   pas l'exécution du push (déjà couverte par `TestPush`).

### Écarts / ajustements

- **`_make_controller` désactive l'auto-sync par défaut**
  (`_auto_sync_done = True`) : sans ça, tous les tests existants qui
  listent de nouveaux fichiers déclencheraient l'auto-sync réelle,
  modifiant l'état et cassant les assertions. Les tests `TestSyncAuto`
  utilisent une fabrique dédiée (`_make_with_files`) qui laisse le flag
  à `False`. Choix documenté dans la docstring de `_make_controller`.

---

## Journal des chantiers

| Chantier | Livrable | Commit | Tests cumulés |
|----------|----------|--------|---------------|
| 1 — 409 → skip | `sync/activities.py` + 4 tests | `da397bf` | 277 |
| 2 — Refresh listes | controllers + vue + 6 tests | `aa559c2` | 283 |
| 3 — Grisement | controller + vue + 9 tests | `1aa3c84` | 292 |
| 4 — Sync auto | controller + 6 tests | `dd73714` | 298 |

**Régression finale** : `pytest tests/ -m unit` → **298 passed** (273
existants + 25 nouveaux). Imports `ui.app`, `ui.watch_view` OK. Aucun
TODO/FIXME.

## Critères de done du brief — état

- [x] Chantier 1 : 409 catché spécifiquement → skip + mark_transferred.
- [x] Chantier 2 : boutons « ↻ » sur les deux listes + refresh auto
      après sync montre.
- [x] Chantier 3 : `hide_transferred` dans ActivitiesController + toggle
      + compteur.
- [x] Chantier 4 : sync auto au branchement avec garde-fous.
- [x] `pytest tests/ -m unit -v` passe à 100 % (298).
- [x] `import openrunner55.ui.app` ne lève pas.
- [x] Aucun TODO non résolu.

## Points à trancher (pour le DP, hors périmètre de cette session)

1. **Dette technique : exception domaine pour le 409** : l'import
   direct `garminconnect` dans `sync/activities.py` est acceptable
   (ADR-002 autorise côté Service) mais un couplage plus propre serait
   de faire remonter `DuplicateActivityError` depuis `garmin/client.py`.
   Chantier ultérieur, pas urgent.

2. **Validation réelle** : la sync auto au branchement n'a pas été
   testée sur montre réelle. À valider au prochain branchement de la
   FR55.

3. **Sync auto descendante (workouts GC → montre)** : hors périmètre
   Epic 5 (nécessite sélection utilisateur). Noté pour plus tard si le
   besoin emerge.

---

## Commandes de vérification

```bash
# Tests unitaires (doit être vert)
.venv/bin/python -m pytest tests/ -m unit -v

# Import des modules UI (doit être muet / OK)
.venv/bin/python -c "import openrunner55.ui.app, openrunner55.ui.watch_view"

# Lancement réel de l'app (validation manuelle Franck : montre branchée)
.venv/bin/python -m openrunner55
```

**Validation manuelle attendue (jalon E5)** : brancher la FR55 → sync
auto déclenchée (nouveaux fichiers envoyés vers GC, barre de
progression visible, résumé affiché) → fichiers transférés masqués par
défaut → bouton « ↻ » pour rafraîchir → toggle « Masquer transférés »
pour les réafficher.
