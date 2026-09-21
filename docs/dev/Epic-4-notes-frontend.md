# Notes de dev frontend — Epic 4 (Historique & logs)

> Document vivant. Consigne les choix, écarts et observations du Developer
> Frontend au fil des étapes de l'Epic 4 frontend. Complète le brief
> (`Epic-4-brief.md`) sans le dupliquer. Source de vérité pour la revue du
> Directeur de Projet.
>
> Branche : `feat/epic-4-history`.

## Environnement (observations initiales)

| Point | Constat | Conséquence |
|-------|---------|-------------|
| Baseline | **248 tests verts** (`-m unit`, `.venv/bin/python`) | Epics 1-3 mergés, socle sain. |
| Python / libadwaita | 3.14.7 / 1.9.3 | Constats Epic 2/3 toujours valables (classes CSS `success`/`warning`/`error`, `monospace`, etc.). |
| Stores Core | `SyncHistoryStore` + `OperationLogger` existants depuis Epic 1/2, peuplés à chaque sync | Backend quasi-néant : 100 % frontend + un wrapper Service. |
| Contract `details` | 2 formats JSON (workouts sans `skipped`, activities avec `skipped`) | Le controller doit parser les deux, robustement. |

---

## Étape 1 — `sync/history.py` (Service) + tests (commit `6b0db64`)

**Livrables** : `sync/history.py` (`HistoryService`), 8 tests. Régression : 256 verts.

### Choix

1. **Wrapper fin en lecture seule**, conforme ADR-002 : l'UI n'appelle jamais
   `store/` directement. Le service importe `SyncRecord`/`LogRecord` depuis
   `store/` (légal : Services → Core) et les **ré-exporte** : le controller
   (UI) les importe depuis `sync/history.py`, jamais depuis `store/`.
2. **`get_operation_logs` n'expose pas `operation`** (le store l'accepte) :
   l'UX §4.2 ne demande que le filtre par niveau. Interface volontairement
   minimale, extension possible plus tard sans casser l'UI.

---

## Étape 2 — `ui/history_controller.py` + tests (commit `9fc22ce`)

**Livrables** : `history_controller.py`, 13 tests. Régression : 269 verts.

### Choix

1. **Miroir de `WorkoutsController`/`ActivitiesController`** : pas d'import
   `gi.repository`, pattern observateur (`on_records_changed` /
   `on_logs_changed`), état exposé en lecture (`records`, `logs`,
   `log_level_filter`). **Aucun threading** : les lectures SQLite sont
   instantanées (50-100 lignes), `refresh()` et `set_log_level_filter()` sont
   synchrones — décision explicite du brief (threader plus tard si besoin).
2. **`refresh()` respecte le filtre actif** : recharge l'historique ET les logs
   en repassant `level=self._log_level_filter`. `set_log_level_filter()` ne
   recharge **que** les logs (jamais l'historique) — test dédié.
3. **Parsing du détail dans le controller** (`parse_record`) : logique de
   présentation, pas métier (ADR-002). Retourne un `SyncRecordDetail` figé
   (`files`, `errors`, `skipped`, `total`).
   - `total = file_count + len(errors) + skipped` → le ratio affiché est
     `file_count / total`.
   - **Le numérateur (`file_count`) reste porté par le `SyncRecord`**, pas
     dupliqué dans le détail (le record le possède déjà).
   - **Robustesse** : `details` à `None`, JSON invalide ou non-objet → détail
     vide et `total = file_count` (ratio `N/N`), jamais d'exception. Cas
     couverts : `None`, JSON malformé, JSON non-dict (`[...]`).

---

## Étape 3 — `ui/history_view.py` + wiring `app.py` (commit `6d8bf7f`)

**Livrables** : `history_view.py`, `app.py` étendu. Aucun test GTK (décision du
brief : couverture UI > 60 % via le controller, ADR-008). Régression : 269
verts. Smoke test GTK (display réel) : construction + refresh + filtre OK.

### Choix

1. **`Gtk.Paned` vertical** (poignée fine) entre les deux zones — même
   discipline que `WatchView` (horizontal). Haut fixe (`resize_start_child
   False`), les logs s'étendent. Classe `.card` pour l'encart unifié.
2. **Tableau d'historique : `Gtk.ListBox` + `Gtk.Revealer`** (SLIDE_DOWN) —
   le brief autorisait ListBox ou ColumnView pour le tableau, et Expander ou
   Revealer pour le détail. Choix ListBox+Revealer : plus léger que ColumnView,
   et l'Expander imposerait une flèche de disclosure qui consommerait la
   première colonne. Ligne `activatable` → clic = toggle du Revealer.
   - Colonnes de résumé : Date (`dd/mm/yyyy HH:MM`, `dim-label`), Direction
     (↓/↑/⇅), Fichiers (`file_count/total`), Statut (✓/⚠/✗ + classe
     `success`/`warning`/`error`).
   - Détail : fichiers réussis (✓), erreurs (✗, `error`, wrappées,
     sélectionnables), skippés (si > 0, `dim-label`).
3. **Logs : `Gtk.ListBox`** (une ligne par log), pas `TextView` — le brief
   autorisait les deux, mais la coloration par niveau via **classes CSS sur le
   label de niveau** (`warning`/`error`) est plus simple par ligne. Chaque
   ligne : `[timestamp]` (dim) `[LEVEL]` (coloré) `message` — tout en
   `monospace`, message wrappé et sélectionnable.
4. **Filtre : 4 `Gtk.ToggleButton` groupés** (Tous/INFO/WARN/ERROR) →
   comportement radio, un seul actif à la fois. « Tous » actif au setup (avant
   connexion du signal, pas de déclenchement parasite). Le handler n'agit que
   sur le bouton devenu actif. `DEBUG` n'a pas de bouton (conforme brief :
   INFO/WARN/ERROR + Tous) ; les logs DEBUG ne s'affichent que sous « Tous »,
   en `dim-label`.
5. **États vides** : « Aucune synchronisation enregistrée » / « Aucun log »
   (labels `dim-label` centrés), bascule `set_visible` entre label vide et
   `ScrolledWindow`.
6. **Formatage timestamp** : `strptime`/`strftime` en `dd/mm/yyyy HH:MM`, avec
   repli sur la chaîne brute si format inattendu (robustesse, jamais de crash).

### Écarts par rapport au brief

| Référence | Écart | Justification |
|-----------|-------|---------------|
| Brief §4 : « Appeler `refresh()` après construction » | **+ refresh à la navigation** (ouverture de la section « Logs & Historique ») | sans cela, l'historique serait figé au lancement : une sync faite dans la section Activité ne serait pas visible en revenant sur Logs & Historique. Charge négligeable (lectures SQLite synchrones). **À valider par le DP.** |
| Brief §3 : ratio « X/Y » | ratio = `record.file_count / detail.total` (numérateur non dupliqué dans le détail) | `file_count` est déjà le nombre de réussis porté par le record ; `total` est la seule valeur à dériver. |

---

## Points à trancher (pour le DP)

1. **Refresh à la navigation (écart ci-dessus)** : j'ai choisi de rafraîchir
   l'historique/logs à chaque ouverture de la section, en plus du refresh
   initial demandé par le brief. Redondance minime, mais garantit des données à
   jour. Si le DP préfère la lecture stricte du brief (refresh initial
   uniquement), retirer 4 lignes dans `_on_nav_selected`.

2. **Granularité de l'historique (héritée Epic 2/3, non corrigée — décision du
   brief)** : les syncs multi-fichiers produisent N entrées « 1/1 » au lieu
   d'une agrégée « X/N ». Affichées telles quelles (verbeux mais honnête). La
   correction (agrégation) reste un chantier séparé, déjà en dette technique.

3. **409 « Duplicate Activity » → skip et retry 5xx (hérités Epic 3, hors
   périmètre Epic 4)** : le brief les note explicitement « backlog » / chantier
   séparé. Non traités ici, mais ils restent les deux gains d'UX prioritaires
   pour la suite (le détail des syncs affichera proprement ces cas une fois
   corrigés côté backend).

---

## Journal des étapes

| Étape | Livrable | Commit | Tests cumulés |
|-------|----------|--------|---------------|
| 1 — service | `sync/history.py` + 8 tests | `6b0db64` | 256 |
| 2 — controller | `ui/history_controller.py` + 13 tests | `9fc22ce` | 269 |
| 3 — vue + wiring | `ui/history_view.py` + `app.py` | `6d8bf7f` | 269 |

**Régression finale** : `pytest tests/ -m unit` → **269 passed** (248 existants
+ 21 nouveaux : 8 service + 13 controller). Imports `ui.app`, `ui.history_view`,
`ui.history_controller`, `sync.history` OK. Smoke test GTK (display réel) :
construction de la vue, refresh, reconstruction des listes, filtre
ERROR → 1 ligne / Tous → 2 lignes → OK. L'UI n'importe jamais `store/`
directement (le controller importe les records depuis `sync/history.py`) ni
`garminconnect`. Aucun mot de passe/token (l'UI ne fait qu'afficher des messages
déjà filtrés par `OperationLogger`). Aucun TODO/FIXME.

## Critères de done du brief — état

- [x] `sync/history.py` créé : `HistoryService` wrapper fin.
- [x] `ui/history_controller.py` créé : logique sans GTK.
- [x] `ui/history_view.py` créé : tableau d'historique + logs filtrables.
- [x] `ui/app.py` étendu : placeholder remplacé, wiring OK.
- [x] `tests/unit/test_history_service.py` créé (8 tests).
- [x] `tests/unit/test_history_controller.py` créé (13 tests).
- [x] `python -m pytest tests/ -m unit -v` : 269 passed (100 %).
- [x] `import openrunner55.ui.history_view` : OK.
- [x] L'UI n'appelle jamais `store/` directement (passe par `sync/history.py`).
- [x] L'UI n'importe jamais `garminconnect`.
- [x] Aucun mot de passe/token dans les logs ou l'UI.
- [x] Pas de TODO non résolu.

## Commandes de vérification

```bash
# Tests unitaires (doit être vert)
.venv/bin/python -m pytest tests/ -m unit -v

# Import des modules UI (doit être muet / OK)
.venv/bin/python -c "import openrunner55.ui.app, openrunner55.ui.history_view, openrunner55.ui.history_controller, openrunner55.sync.history"

# Lancement réel de l'app (validation manuelle Franck)
.venv/bin/python -m openrunner55
```

**Validation manuelle attendue** : lancer l'app → naviguer vers « Logs &
Historique » → voir le tableau des syncs passées (date, ↓/↑, ratio, statut) et
les logs en dessous ; cliquer une ligne → détail fichiers/erreurs/skippés ;
filtrer les logs par INFO/WARN/ERROR ; après une sync dans la section Activité,
revenir sur Logs & Historique → les nouvelles entrées sont visibles.
