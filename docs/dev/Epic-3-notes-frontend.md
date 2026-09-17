# Notes de dev frontend — Epic 3 (Activités Montre → Garmin Connect)

> Document vivant. Consigne les choix, écarts et observations du Developer
> Frontend au fil des étapes de l'Epic 3 frontend. Complète le brief
> (`Epic-3-brief-frontend.md`) sans le dupliquer. Source de vérité pour la
> revue du Directeur de Projet.
>
> Branche : `feat/epic-3-frontend`.

## Environnement (observations initiales)

| Point | Constat | Conséquence |
|-------|---------|-------------|
| Baseline | **205 tests verts** (`-m unit`, `.venv/bin/python`) | Epic 1 + 2 + 3 backend mergés, socle sain. |
| Python / libadwaita | 3.14.7 / 1.9.3 | Constats Epic 2 toujours valables (scheduler `GLib.idle_add`, classes CSS, etc.). |
| `WatchDetector.on_status_changed` | Liste de callbacks (multi-abonnés) | Les deux controllers (`WorkoutsController`, `ActivitiesController`) s'abonnent indépendamment au detector partagé — pas de relais par l'app nécessaire. |
| GTK build local | `Button.activate()` retourne `True` **sans émettre `clicked`** | Artefact de test uniquement : les smoke tests émettent `clicked` explicitement (comme le ferait un clic réel). Sans impact sur l'app. |

---

## Étape 1 — `ui/activities_controller.py` + tests (commits `2208445`, `4b0659b`)

**Livrables** : `activities_controller.py` (~400 lignes),
`tests/unit/test_activities_controller.py` (30 tests). Régression : 235 verts.

### Choix

1. **Miroir exact de `WorkoutsController`** : pas d'import `gi.repository`,
   types Core sous `TYPE_CHECKING` uniquement, dépendances injectées
   (duck-typing), `watch_factory: Callable[[Path], WatchFilesystem]`,
   scheduler injectable (synchrone par défaut pour les tests,
   `GLib.idle_add` en production). Toute la logique métier vient de
   `sync/activities.py` (contrats figés respectés à la lettre).

2. **`WatchNotConnectedError` réutilisée** depuis `workouts_controller`
   (même couche UI, même sémantique) — pas de duplication de classe.

3. **Progression par fichier** : le contrat figé `push_activities(items) ->
   SyncResult` n'expose aucun callback de progression. Le worker boucle donc
   sur `push_activities([item])` par fichier et agrège les bilans
   (total/success/failed/errors/skipped) — pattern déjà acté en Epic 2.
   **Conséquence assumée** : une entrée `sync_history` par fichier au lieu
   d'une entrée agrégée (même point de vigilance qu'Epic 2, cf. § Points à
   trancher).

4. **Sort de la sélection après envoi** (possible grâce à la boucle
   unitaire) : envoyés **et skippés** décochés ; échoués **restent cochés**
   (parcours C, exigence du brief). Le cas « skippés décochés s'ils étaient
   sélectionnés » est couvert par un test dédié.

5. **Listing différé au branchement** : `list_uploadable_files_async`
   mémorise `on_done`/`on_error` et ne lance rien si la montre est déconnectée
   ; `on_watch_status_changed(True)` déclenche le lancement (garde
   `is_loading` anti-re-entrante). La vue n'a pas à s'abonner au détecteur :
   **un seul chemin de déclenchement du listing**, celui du brief.
   Sémantique des callbacks : « dernier enregistré gagne », y compris quand le
   lancement est gardé (documenté en test).

6. **Pré-sélection automatique** : après listing réussi,
   `selected = {f.path for f in files if not f.already_transferred}` —
   décision de cadrage « UX de la première sync » du brief.

7. **Reflet local du store** : après un upload réussi, l'objet
   `UploadableFile` en mémoire passe `already_transferred=True` → la ligne
   s'estompe sans re-listing USB. Ce n'est pas de la logique métier (le
   backend a déjà écrit en SQLite via `push_activities`) ; c'est un cache
   d'affichage.

8. **Résultat périmé discardé** : si la montre est débranchée pendant le
   chargement, `_on_list_success` jette le résultat (la liste a déjà été
   vidée par le signal de débranchement).

### Écarts par rapport au brief

| Référence | Écart | Justification |
|-----------|-------|---------------|
| `push_activities` (batch unique) | appel par fichier dans le worker | progression « avant chaque fichier » impossible autrement (contrat figé sans callback) — même arbitrage qu'Epic 2 |
| API du controller (brief) | + `watch_connected` | la vue a besoin de l'état suivi pour la bascule placeholder/contenu (comme en Epic 2) |
| `list_uploadable_files_async(on_done, on_error)` | callbacks mémorisés + lancement différé au branchement | le brief exige que `on_watch_status_changed(True)` lance le listing ; cette mécanique est la seule qui évite que la vue s'abonne elle-même au détecteur |

---

## Étape 2 — zone Montre fonctionnelle + wiring (commit `8cc3930`)

**Livrables** : `watch_view.py` étendu, +5 tests `_format_size`. Régression :
240 verts. Smoke test GTK réel : OK.

### Choix

1. **Signature `WatchView(controller, activities_controller=None)`** : sans
   second controller, la zone Montre retombe sur le placeholder Epic 2
   (dégradation gracieuse, tests Epic 2 intacts). Le wiring
   d'`ActivitiesController` se fait dans `app.py` (composition root, exception
   Core déjà documentée et validée en Epic 2) : mêmes dépendances, **même
   instance de `WatchDetector`**, `scheduler=GLib.idle_add`.

2. **Ligne de fichier sobre** (UX §4.1) : `Gtk.CheckButton` + nom
   (`path.name`, ellipsize Pango) + libellé secondaire grisé
   « Catégorie · taille · déjà transféré ». Ligne estompée (`dim-label`) si
   `already_transferred`. Pas de regroupement par catégorie (choix laissé au
   dev dans le brief — la liste backend est déjà triée par catégorie).
   La **taille** répond à US-3.1 ; la date n'est pas affichée séparément (le
   nom `Activity/…` est déjà le timestamp — pas de décodage FIT, ADR-002).

3. **Bouton toggle « Tout sélectionner/désélectionner »** : le libellé
   reflète l'**action disponible**, pas l'état ; inactif pendant le
   chargement et sur liste vide.

4. **Anti-rebouclage checkboxes** : même discipline que la zone GC —
   `set_active` avant `connect("toggled")` + flag `_watch_syncing`.

5. **Clic « Synchroniser » non branché à cette étape** : volontairement, pour
   éviter tout code mort anticipé (impossible à déclencher avant le listing
   de l'étape 3). Branché à l'étape 4 avec progression + résumé.

---

## Étape 3 — chargement threadé de la liste (commit `9805463`)

**Livrables** : spinner, déclenchement différé, message d'erreur. Régression :
240 verts. Smoke test GTK (scheduler de production `GLib.idle_add`, thread
réel) : OK.

### Choix

1. **La vue appelle `list_uploadable_files_async` à la construction** ; le
   controller diffère au branchement si la montre est déconnectée. Aucun
   abonnement de la vue au `WatchDetector`.

2. **Spinner** centré pendant `is_loading` (liste masquée), stoppé/masqué à la
   fin — discipline identique à la zone GC.

3. **Erreur de listing = message générique** (« Impossible de lire les
   fichiers de la montre. Vérifiez le câble USB… »), jamais l'exception brute
   (cohérent UX §4.4 et zone GC). L'erreur s'efface au rechargement réussi et
   au débranchement.

---

## Étape 4 — envoi threadé (commit `f274fc7`)

**Livrables** : progression, résumé avec `skipped`, clic branché. +7 tests
`_format_activity_summary`. Régression : 247 verts. Smoke test GTK (cycle
complet) : OK.

### Choix

1. **Barre de progression dans un `Gtk.Revealer`** (`SLIDE_UP`, bas de la
   zone) — le brief autorisait Revealer ou overlay ; le Revealer évite un
   overlay qui masquerait la liste. Texte « Fichier X/N — {nom} » + pourcentage.
   Pas de bouton d'annulation (cohérent Epic 2).

2. **Résumé d'envoi** (`_format_activity_summary`, logique pure testée) :
   succès total / partiel / total, avec suffixe « · M skippés » quand
   `skipped > 0` — l'utilisateur comprend un `success < total`. Détails
   d'erreur préformatés affichés **tels quels** (contrat backend figé).
   Label **sélectionnable** → copiable pour le support.

3. **Erreur fatale d'envoi** (montre débranchée avant le premier upload) :
   message utilisateur dans le résumé, pas l'exception brute.

4. **Vérifié empiriquement dans le smoke** : `already_transferred` sélectionné
   → **aucun appel** `upload_activity` (skip backend, délai 3 s évité) ;
   `skipped` reporté dans le résumé ; bouton verrouillé pendant l'envoi ;
   échoué reste coché ; ligne envoyée s'estompe.

---

## Points à trancher (pour le DP, hors périmètre de cette session)

1. **Granularité de l'historique (hérité Epic 2, désormais aussi côté
   montée)** : la boucle unitaire `push_activities([item])` produit N entrées
   `sync_history` « 1/1 » au lieu d'une entrée agrégée « X/N ». Affectera
   l'UX §4.2 (Epic 4). Deux options propres : callback de progression dans le
   contrat backend (casserait le gel) ou agrégat d'historique côté Epic 4.

2. **Statut de la ligne après envoi réussi** : le reflet local
   (`already_transferred=True` en mémoire) se perd au prochain re-listing
   — sans gravité, le store SQLite est la vérité et le re-listing le relit
   correctement. Comportement cohérent, noté pour mémoire.

3. **Pagination** (veille brief, > 200 fichiers) : la `Gtk.ListBox` rend 200
   lignes sans difficulté mesurée ; non testé au-delà. À surveiller en E4.

---

## Journal des étapes

| Étape | Livrable | Commit | Tests cumulés |
|-------|----------|--------|---------------|
| 1 — controller | `activities_controller.py` + 30 tests | `2208445`, `4b0659b` | 235 |
| 2 — vue | zone Montre fonctionnelle + wiring `app.py` + 5 tests | `8cc3930` | 240 |
| 3 — listing threadé | spinner + différé branchement + erreur | `9805463` | 240 |
| 4 — envoi threadé | progression + résumé skippés + 7 tests | `f274fc7` | 247 |

**Régression finale** : `pytest tests/ -m unit` → **247 passed** (205 existants
+ 42 nouveaux : 30 controller + 12 vue). Imports `ui.app`, `ui.watch_view`,
`ui.activities_controller` OK. Smoke tests GTK (display réel, scheduler de
production, threads réels) : cycle listing + erreurs + envoi complet → OK.
Aucun `garminconnect` importé par l'UI (vérifié par grep — seule occurrence :
mention documentaire dans un docstring Epic 1/2). Aucun appel Core direct hors
composition root `app.py` (imports vérifiés un à un : le controller n'importe
que `sync/` + l'UI ; la vue n'importe `sync/` que pour les dataclasses
`SyncResult` d'affichage). Aucun mot de passe/token dans l'UI (l'Epic 3
frontend ne touche aucun credential). Aucun TODO/FIXME.

## Critères de done du brief — état

- [x] `watch_view.py` étendu : liste, sélection, « Synchroniser », progression, résumé, pré-sélection, indication `already_transferred`.
- [x] `activities_controller.py` : logique sans GTK.
- [x] `tests/unit/test_activities_controller.py` : 30 tests.
- [x] `pytest tests/ -m unit -v` : 247 passed (100 %).
- [x] `import openrunner55.ui.watch_view` : OK.
- [x] Aucun appel réseau/USB sur le thread GTK (threads + `GLib.idle_add`, vérifié en smoke avec scheduler de production).
- [x] Aucun mot de passe/token dans logs ou UI.
- [x] UI n'importe jamais `garminconnect`.
- [x] UI n'appelle pas `garmin/`, `watch/`, `store/` directement (sauf `WatchDetector`, validé DP Epic 2 ; `app.py` = composition root, exception documentée Epic 2).
- [x] Pas de TODO non résolu.

## Commandes de vérification

```bash
# Tests unitaires (doit être vert)
.venv/bin/python -m pytest tests/ -m unit -v

# Import des modules UI (doit être muet / OK)
.venv/bin/python -c "import openrunner55.ui.app, openrunner55.ui.watch_view, openrunner55.ui.activities_controller"

# Lancement réel de l'app (validation manuelle Franck : montre branchée)
.venv/bin/python -m openrunner55
```

**Validation manuelle attendue (jalon E3)** : brancher la FR55 → la liste se
charge seule (spinner → lignes, nouveaux fichiers pré-cochés) ; décocher/cocher,
« Tout sélectionner » ; « ↻ Synchroniser (N) » → progression par fichier, résumé
avec skippés ; débrancher en cours de route → placeholder + erreur propre.
