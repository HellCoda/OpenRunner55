# Notes de dev frontend — Epic 2 (Workouts Cloud → Montre)

> Document vivant. Consigne les choix, écarts et observations du Developer
> Frontend au fil des étapes de l'Epic 2. Complète le brief
> (`Epic-2-brief-frontend.md`) sans le dupliquer. Source de vérité pour la
> revue du Directeur de Projet.
>
> Branche : `feat/epic-2-frontend`.

## Environnement (observations initiales)

| Point | Constat | Conséquence |
|-------|---------|-------------|
| libadwaita | **1.9.3** | `Adw.NavigationSplitView.set_sidebar`/`set_content` attendent un **`Adw.NavigationPage`** (pas un widget brut). L'API a évolué depuis le wireframe (`Gtk.ListBox` nu). |
| Python | 3.14.7 (venv `.venv`) | `requires-python >=3.12` → OK. |
| pytest | 9.1.1 | Baseline au démarrage : **151 tests verts** (`-m unit`). |
| GTK | import OK, display `:0`/Wayland dispo | Smoke test headless réalisable (construction du shell validée sans lancer l'app complète). |

---

## Étape 1 — `ui/workouts_controller.py` + tests (commit `102289e`)

**Livrables** : `workouts_controller.py` (377 lignes), `tests/unit/test_workouts_controller.py`
(22 tests). Régression : 173 tests verts.

### Choix

1. **Aucun import Core à l'exécution.** Le controller n'importe que
   `sync/workouts.py` (Service). Les types Core (`GarminClient`,
   (annotations) : les objets sont injectés (duck-typing) et passés tels quels
   à `fetch_workouts`/`push_workouts`. Satisfait « l'UI n'importe pas le Core »
   au niveau du controller.

2. **Scheduler injectable.** `__init__(..., scheduler=None)` avec défaut
   `_direct_scheduler` (invocation synchrone, pour les tests). En production la
   vue passe `GLib.idle_add` pour marshaller les callbacks vers le thread GTK.
   Le controller ne dépend donc pas de GTK.

3. **Écart signature — `watch` → `watch_factory`.** Le brief spécifie
   `watch: WatchFilesystem` ; j'injecte `watch_factory: Callable[[Path], WatchFilesystem]`.
   Raisons :
   - le point de montage est **dynamique** (change à chaque branchement) — une
     instance figée pointerait un point de montage périmé ;
   - le controller ne doit pas importer `watch/filesystem.py` (règle Core).
   La factory résout le point de montage courant (`detector.get_mount_path()`)
   au moment de l'envoi, et lève `WatchNotConnectedError` (erreur fatale → `on_error`)
   si la montre est débranchée avant le premier download.

4. **`push_workouts` appelé une fois par workout** (boucle dans le worker).
   Le brief exige `on_progress` « avant chaque workout » mais le contrat backend
   figé `push_workouts(...) -> SyncResult` ne fournit **aucun callback de
   progression** (boucle interne opaque). Seule façon d'émettre une progression
   par workout : découper le batch en appels unitaires, agréger les `SyncResult`
   en fin de boucle.
   **Conséquence assumée** : un `history.log_sync("down", 1, …)` par workout au
   lieu d'une entrée agrégée (le ratio « 8/10 » de l'UX §4.2 en pâtira — à
   trancher pour l'Epic 4).

5. **Les workouts réussis sont décochés après envoi** (`_on_push_success`
   retire les `succeeded_ids` de la sélection). Les échoués restent cochés pour
   réessayer (UX parcours C). Implique que le controller connaît le succès par
   id — possible car il boucle lui-même (point 4).

6. **Propriété `watch_connected` ajoutée** au-delà du contrat du brief : la
   zone Montre placeholder affiche « Branchez votre montre FR55 en USB » vs
   « Réservé à l'Epic 3 » selon la connexion. Le controller expose l'état suivi
   (initialisé depuis `detector.is_connected()`, mis à jour via
   `on_watch_status_changed`).

### Écarts par rapport au brief

| Référence | Écart | Justification |
|-----------|-------|---------------|
| `watch: WatchFilesystem` | `watch_factory: Callable[[Path], WatchFilesystem]` | point de montage dynamique + règle « pas d'import Core » |
| `push_workouts` (batch unique) | appel par workout | progression « avant chaque workout » impossible autrement (contrat figé sans callback) |
| API du controller (brief) | + `watch_connected`, + `scheduler` | nécessaires à la vue (placeholder montre) et à l'injection du marshalling GTK |

---

## Étape 2 — `ui/watch_view.py` + test (commit `6be028f`)

**Livrables** : `watch_view.py`, `tests/unit/test_watch_view.py` (5 tests).
Régression : 178 tests verts.

### Choix

1. **Split 40/60 via `Gtk.Paned`** (`set_position(360)`, `resize_end_child=True`).
   Le ratio est approximatif (la position est en pixels, pas en %) — acceptable
   MVP (l'UX tolère un basculement empilé sous 900 px « futur »).

2. **Checkbox sans rebouclage.** `set_active()` **avant** `connect("toggled")`
   à la construction, plus un flag `_syncing` pour la resynchronisation de
   l'état après un changement de sélection (après un envoi notamment). Évite
   la boucle `toggled` ↔ `toggle_selection`.

3. **La vue se rafraîchit via les callbacks enregistrés** (`on_workouts_changed`,
   `on_selection_changed`, `on_sending_state_changed`) et relit l'état exposé.
   Les callbacks par-appel (`on_done`, `on_error`, `on_progress`) ne servent
   qu'aux **erreurs** (non conservées dans l'état). `on_progress`/`on_done`
   sont des no-op : l'état (`progress`, `last_result`) est déjà lu par la vue.

4. **`_format_summary` pur et testé** (succès/partiel/échec, singulier/pluriel).
   Seule logique pure de la vue — cohérent avec le pattern `test_auth_view.py`
   (instanciation GTK hors périmètre, ADR-008).

5. **libadwaita 1.9.3** : `Gtk.Paned`, `Gtk.ProgressBar.set_show_text/set_text`,
   classes CSS `card`/`title-2`/`dim-label`/`success`/`error` — validées par
   smoke test (construction réelle avec display).

---

## Étape 3 — `ui/app.py` (commit `0035df4`)

**Livrables** : `app.py` étendu (shell post-auth complet). Régression : 178 tests.

### Choix / décisions

1. **Composition root dans `app.py`.** Ce module importe le Core
   (`garmin/client.py`, `store/*`, `watch/filesystem.py`) **uniquement pour la
   construction/wiring du graphe d'objets** (ADR-002), jamais pour de la logique
   métier. Les vues/controller n'importent pas le Core. C'est l'exception de
   composition root : sans elle, personne ne peut construire `GarminClient`,
   les stores SQLite ni la factory `WatchFilesystem` (le brief ne fournit aucun
   bootstrap Service pour ça). Documenté dans le docstring du module — **à
   valider par le DP** (tension avec le critère « l'UI n'appelle jamais Core
   directement », cf. section « Points à trancher »).

2. **`WatchDetector.start()` post-auth, `stop()` sur `close-request`.** L'app
   détient l'instance (`self._detector`), la puce HeaderBar est mise à jour par
   `on_status_changed` (thread-safe). Pas de bouton « ↻ Synchroniser » (Epic 3).

3. **Navigation : `Adw.NavigationSplitView`** avec sidebar `Gtk.ListBox`
   (3 entrées) + contenu `Gtk.Stack` (3 vues nommées). La sélection par défaut
   est « Activité ». Les sections Logs & Compte sont des placeholders
   « titre + À venir ».

4. **`Adw.NavigationPage`** : `set_sidebar`/`set_content` requièrent un
   `Adw.NavigationPage.new(widget, titre)` en libadwaita 1.9.3 (API récente).

5. **Indicateur montre** : puce `Gtk.Label("●")` + label texte
   (« Montre connectée/déconnectée »). Couleur via classes `success`/`dim-label`
   (thème libadwaita, clair/sombre). Le texte accompagne la couleur → accessible.

---

## Points à trancher (bloquants pour le jalon E2, hors périmètre de cette session)

1. **SQLite cross-thread (⚠️ bloquant E2).** `push_workouts` s'exécute dans le
   thread worker (exigence « aucun réseau sur le thread GTK ») mais écrit en
   SQLite via `transfers.mark_transferred` / `history.log_sync` /
   `logger.log`. Or `store/database.py` ouvre la connexion avec
   `sqlite3.connect(...)` → `check_same_thread=True` (défaut). **Au runtime,
   `push_workouts` lèvera `sqlite3.ProgrammingError`** dès la première écriture
   hors du thread GTK. Les tests unitaires ne le voient pas (stores mockés).
   **Recommandation** : `check_same_thread=False` dans `database.py` (un seul
   écrivain à la fois dans l'app ; SQLite sérialise de toute façon). C'est un
   changement backend à acter avant le jalon E2.

2. **Composition root.** Confirmer que `app.py` peut importer le Core pour le
   câblage (exception documentée) — ou prévoir un module bootstrap dédié.

3. **Granularité de l'historique.** `push_workouts` par workout → N entrées
   `sync_history` « 1/1 » au lieu d'une entrée « X/Y ». À trancher (affecte
   l'UX §4.2 de l'Epic 4).

4. **Ratio du split 40/60.** Après la refonte UI (section suivante), le split
   est fait par une zone gauche à largeur fixe (`size_request(360)`) + séparateur
   fin, la zone droite absorbant le reste. Ratio approximatif (~40/60 à 900 px),
   pas strict. Accepté par Franck.

---

## Itération UI (retour Franck, commit `b1eccf1`)

Franck a validé le fonctionnement (app lancée, montre reconnue) mais relevé des
défauts cosmétiques. Corrections apportées :

1. **Panneau Activité unifié** : les deux cartes séparées (`Gtk.Paned` + poignée
   large) sont remplacées par **un seul panneau `.card`** contenant les deux
   zones + un `Gtk.Separator` vertical fin au milieu. Répond à « zone groupée
   comme un tableau unifié avec le séparateur au milieu ».
2. **Titres cohérents** : en-têtes identiques (titre `title-2` + sous-titre
   `dim-label`). La zone Montre a un sous-titre « Activités » qui équilibre le
   « Workouts (N) » de GC.
3. **Alignement haut** : marge haute du panneau supprimée pour s'aligner sur la
   barre latérale (fini le « panel gauche plus haut »).
4. **Coin haut-droit arrondi de la sidebar** : CSS applicatif (`_CUSTOM_CSS` dans
   `app.py`) qui applique `border-top-right-radius: 12px` à la classe interne
   `sidebar-pane` de `Adw.NavigationSplitView`. Le thème libadwaita ne le fait
   pas par défaut (coin carré). Rayon aligné sur celui de `.card` (12 px).
   Chargé via `Gtk.StyleContext.add_provider_for_display` à `on_activate`.

Observation : la session tourne en **thème sombre** (`color-scheme=prefer-dark`,
gtk-theme `Sweet-Dark-v40` — ce dernier n'affecte pas les apps libadwaita, qui
utilisent la palette Adwaita sombre).

> Note : le Developer Frontend ne peut pas visualiser les captures d'écran
> (modèle sans entrée image). Les corrections sont faites d'après la description
> écrite de Franck, et la validation visuelle finale lui revient.

---

## Itération UI 2 (barre bleue + accent Garmin, commit `1185015`)

Franck a demandé : une barre bleue Garmin (`#1976d2`) pleine largeur, sous la
HeaderBar, intégrant l'indicateur de montre (et réservant la place à droite pour
le bouton « Synchroniser » de l'Epic 3). Le bouton « Envoyer » et le fond des
checkboxes cochées doivent être de la même couleur.

Implémentation :

1. **Barre bleue** : `Gtk.Box` (classe `.garmin-bar`) inséré entre la HeaderBar
   et la `NavigationSplitView`, dans le contenu du `Adw.ToolbarView`. L'indicateur
   de montre y a migré (texte blanc sur bleu : pleine opacité connecté,
   `dim-label` déconnecté). Un espaceur `hexpand` réserve la droite.
2. **Accent `#1976d2`** : tentative d'override de la variable `--accent-bg-color`
   via `:root` → **échec** (l'accent est piloté par `Adw.StyleManager` via le
   réglage système `accent-color` — ici `purple`). Solution retenue : règles CSS
   **directes** sur les widgets concernés :
   ```css
   button.suggested-action { background-color: #1976d2; color: #fff; }
   check:checked, check:indeterminate { background-color: #1976d2; color: #fff; }
   ```
   Les états hover/active du bouton (overlay `background-image` du thème)
   restent fonctionnels par-dessus la couleur de base.
3. **Vérification empirique** : rendu GTK en PNG + échantillonnage de pixels
   (`Gtk.Snapshot` + `Gsk.CairoRenderer`). La barre bleue et le fond de checkbox
   cochée ressortent exactement en `srgba(25,118,210,1)` = `#1976d2`.

Observation : session en thème sombre, accent système **violet** (`accent-color`
= purple). Le choix `#1976d2` est donc bien un override app-local, pas un simple
repli sur l'accent système.

---

## Journal des étapes

| Étape | Livrable | Commit | Tests cumulés |
|-------|----------|--------|---------------|
| 1 — controller | `workouts_controller.py` + tests | `102289e` | 173 |
| 2 — vue | `watch_view.py` + test | `6be028f` | 178 |
| 3 — shell | `app.py` | `0035df4` | 178 |

**Régression finale** : `pytest tests/ -m unit` → **178 passed** (151 existants
+ 27 nouveaux). Imports `ui.app`, `ui.watch_view`, `ui.workouts_controller` OK.
Smoke test GTK (display réel) : construction du shell + navigation + fetch
async + cycle de vie `WatchDetector` → OK. Aucun `garminconnect` importé par
l'UI. Aucun credential dans les logs/UI (rien de nouveau à ce niveau).

---

## Commandes de vérification

```bash
# Tests unitaires (doit être vert)
.venv/bin/python -m pytest tests/ -m unit -v

# Import des modules UI (doit être muet / OK)
.venv/bin/python -c "import openrunner55.ui.app, openrunner55.ui.watch_view, openrunner55.ui.workouts_controller"

# Lancement réel de l'app
.venv/bin/python -m openrunner55
```
