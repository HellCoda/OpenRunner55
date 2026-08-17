# Notes de dev backend — Epic 2 (Workouts Cloud → Montre)

> Document vivant. Consigne les choix, écarts et observations du Developer
> Backend au fil des étapes de l'Epic 2. Source de vérité pour la revue du
> Directeur de Projet ; complète le brief (`Epic-2-brief.md`) sans le dupliquer.
>
> Branche : `feat/epic-2-workouts`.

## Environnement (observations initiales)

| Point | Constat | Conséquence |
|-------|---------|-------------|
| `pyudev` | **Absent du `.venv`** (présent en Python système, v0.24.4) | L'import doit être **optionnel** dans `watch/detector.py`, sinon `import openrunner55.watch.detector` échoue dans le venv. Déclaré + installé dans le venv. |
| `GLib` (PyGObject) | Présent (v3.50) | Le marshalling `GLib.idle_add` fonctionne ; garder un repli direct pour les tests sans boucle GTK. |
| `pytest` | 9.1.1, venv `.venv` | Baseline au démarrage : **72 tests verts** (`-m unit`). |
| Python | 3.14.6 (venv) | `requires-python >=3.12` → OK. |

---

## Étape 1 — `watch/detector.py` (livré, commit `88e9d20`)

**Livrables** : `watch/__init__.py`, `watch/detector.py`, `tests/unit/test_detector.py`
(15 tests), `pyproject.toml` (+`pyudev>=0.24`). Régression : 87 tests verts.

### Choix

1. **`start()` / `stop()` ajoutés** au-delà des 3 méthodes du contrat.
   Le brief dit « le détecteur est démarré au lancement post-auth (côté
   frontend) » → il faut un point d'entrée. Idempotent, thread daemon, `stop()`
   joint avec timeout 2 s.

2. **Import optionnel de `pyudev`** (try/except → `_pyudev = None`), tout en le
   déclarant dans `pyproject.toml`. Repli sur le polling seul si absent. Couvre
   aussi le critère « testable sans montre branchée ».

3. **Émission du signal** : module-level `_emit_thread_safe(callback, connected)`
   → `GLib.idle_add` si GLib dispo (ADR-006), sinon invocation directe. Les
   tests neutralisent `_GLib` (fixture `direct_emit`) pour observer les
   callbacks de façon synchrone, sans boucle GTK.

4. **Un seul thread** pour monitor + polling. `monitor.poll(timeout=poll_interval)`
   sert de tick au polling : retourne `None` sur timeout (→ re-vérification),
   un `Device` sur événement. Un événement au label `GARMIN` déclenche une
   re-vérification immédiate. Économise un thread et un `sleep` dédié.

5. **Confirmation = `is_file()`**, pas `exists()` : un dossier homonyme
   `GarminDevice.xml` ne doit pas compter comme une FR55.

### Écarts par rapport au brief / ADR

| Référence | Écart | Justification |
|-----------|-------|---------------|
| ADR-006 (« événements `bind`/`unbind` ») | Déclencheur = **label `GARMIN`** (`ID_FS_LABEL`) plutôt que l'action udev précise | Le polling couvre tout ; filtrer sur le label évite de re-vérifier sur chaque événement block sans rapport. `bind`/`unbind`/`add`/`remove` sont tous traités via le label. |
| Contrat brief (3 méthodes) | `start()`/`stop()` ajoutés | Nécessaire pour le cycle de vie (démarrage post-auth). Documenté dans le docstring. |

### Observé / à retenir

- `get_mount_path()` renvoie le **point de montage du volume** (`/run/media/$USER/GARMIN`),
  pas la racine interne `GARMIN/`. Cohérent avec l'étape 2 (`WatchFilesystem`
  base = `{mount_path}/GARMIN/`).

---

## Points tranchés au fil des étapes (tous résolus)

- **[Étape 4] `download_workout`** : le brief impose `return self._call("download_workout", workout_id)`.
  Vérifier la signature réelle de `garminconnect.Garmin.download_workout` (le
  spike-S2 utilise `garmin.download_workout(workoutId)` → cohérent, 1 seul arg).
- **[Étape 5] `fetch_workouts` (tri)** : le brief dit « tri sur le champ date de
  la réponse API GC ». Le nom exact du champ (ex. `createdDate`, `updatedDate`,
  `modifiedDate`) est à confirmer sur une réponse réelle de `get_workouts()` —
  à recaler si besoin dans `docs/exploration/spike-S2-resultat.md`.
- **[Étape 5] `push_workouts`** : le brief liste 7 étapes dont la **collision**
  (`{slug}_2.FIT`…) et le `history.log_sync("down", ...)`. Statut final
  `success`/`partial`/`failed` à dériver de `SyncResult` (0 échec → success,
  tout échoué → failed, sinon partial).
- **[Étape 3] `transferred_files`** : colonne `file_hash` prévue mais NULL au
  MVP — la dédup se fait sur `(file_name, direction, source)` (ADR-005).
  Le brief signature `mark_transferred(file_name, direction, source, gc_activity_id=None)`
  ne prend pas `file_hash` → OK, on ne le remplit pas.

---

## Étape 2 — `watch/filesystem.py` (livré, commit `cba31ae`)

**Livrables** : `watch/filesystem.py`, `tests/unit/test_filesystem.py` (12 tests).
Régression : 99 tests verts.

### Choix

1. **Convention de chemin relatif** : les méthodes prennent/retournent des chemins
   **relatifs à `GARMIN/`** (ex. `Path("Workouts/foo.FIT")`). Un chemin retourné
   par `list_fit_files()` est directement utilisable avec `read_fit`/`write_fit`.
   Le module résout l'absolu en interne — le service n'a pas à connaître le
   point de montage.
2. **Extension `.FIT` insensible à la casse** : FAT32 (casse-insensible) ; la
   montre mélange `.fit`/`.FIT` (cf. `tree-FR55.md`). Filtre `suffix.lower() == ".fit"`.
3. **`list_fit_files` ignore les sous-dossiers** (`Workouts/Guided`,
   `Workouts/Schedule`) et les fichiers non-FIT.
4. **Catégorie invalide → `ValueError`** (fail fast, évite un bug silencieux).

### Écart ADR/brief

| Référence | Écart | Justification |
|-----------|-------|---------------|
| ADR-002 : `write_fit(...) -> bool` | `-> None` + levée `OSError` | Le brief Epic 2 l'impose explicitement (« ne retourne pas de booléen silencieux »). Cohérent avec `read_fit`/`Path.write_bytes` qui lèvent déjà `OSError`. |

---

## Étape 3 — `store/transfers.py` + `store/history.py` (livré, commit `30db015`)

**Livrables** : `store/transfers.py`, `store/history.py`, `store/__init__.py`
(extension exports), `tests/unit/test_transfers.py` (11), `tests/unit/test_history.py`
(10). Régression : 120 tests verts.

### Choix / décisions

1. **`is_transferred(file_name, direction, source=None)`** — concilie le brief
   (2 args, nom `is_transferred`) et l'ADR-005 (`is_already_transferred`, 3 args,
   dédup sur `(file_name, direction, source)`). `source` optionnel : sans lui,
   comportement exact du brief ; avec lui, dédup précise. Validé par Franck.
2. **`file_hash` NULL au MVP** — `mark_transferred` ne calcule pas de SHA256.
3. **Validation des enums en `ValueError`** (direction, source, status) en amont
   des contraintes CHECK SQLite : erreur claire plutôt qu'un `IntegrityError` brut.
4. **`details` stocké tel quel** (TEXT) : c'est le service qui fournit la chaîne
   JSON déjà sérialisée (`history.log_sync(..., details_json)`). Le store ne
   transforme pas.
5. **`store/__init__.py` étendu** pour exporter `TransferredFilesStore`,
   `SyncHistoryStore`, `SyncRecord` (cohérence avec l'export existant).

### Observé / à retenir

- `mark_transferred` n'a **pas de contrainte d'unicité** : re-marquer le même
  fichier crée une ligne dupliquée (sans impact fonctionnel, `is_transferred`
  reste True). Un index unique `(file_name, direction, source)` est envisageable
  en migration si besoin. Noté dans le docstring du module.
- `SyncRecord` est un dataclass `frozen=True` (comme `LogRecord`) — immuable.

---

## Étape 4 — extension `garmin/client.py` (livré, commit `278306a`)

**Livrables** : `garmin/client.py` (méthode `download_workout`), extension
`tests/unit/test_garmin_client.py` (+5 tests). Régression : 125 tests verts.

### Choix

- **`download_workout(workout_id) -> bytes`** via `return self._call("download_workout", workout_id)`,
  exactement comme le brief l'impose. Aucune logique ajoutée : délai 3 s, retry
  429 et re-login 401 sont hérités de `_call()`/`_invoke()`.
- Docstring du module mise à jour (les méthodes Epic 2 sont désormais exposées).
- Tests ajoutés : retour bytes, forwarding de l'ID, héritage du délai 3 s,
  retry 429, re-login 401 (le 401 confirme le passage par `_call`).

### Point levé en note → résolu

Le champ date pour `fetch_workouts` (étape 5) sera vérifié dans `spike-S2` à
l'étape 5, comme convenu.

---

## Étape 5 — `sync/workouts.py` (livré, commit `1987966`)

**Livrables** : `sync/__init__.py`, `sync/workouts.py`, `tests/unit/test_sync_workouts.py`
(23 tests). Régression : 148 tests verts. Couverture nouveaux modules : **95 %**
(transfers/history/filesystem 100 %, workouts 98 %, detector 86 % — les branches
non couvertes du detector sont celles du monitor pyudev, intouchables sans udev).

### Vérification (champ date) — résolue

Confirmé dans `spike-S2/python-garminconnect` :
- `get_workouts()` retourne des dicts `{workoutId, workoutName, sportType{...},
  updatedDate, createdDate}`. Dates au format `"2018-07-05T17:34:04.0"`
  (parsable par `datetime.fromisoformat`).
- `sportType.sportTypeKey` = sport lisible (ex. `"running"`).

**Décision** : tri sur `updatedDate` en priorité (reflète la dernière
modification), repli sur `createdDate` ; si les deux sont absentes/non
parsables → `date = None` et l'élément est placé en fin de liste en conservant
l'ordre API (tri stable, clé `datetime.min`).

### Choix / décisions

1. **`WorkoutSummary.date` typé `datetime | None`** (le brief dit `datetime`,
   mais « si la date est absente » implique None). Écart mineur documenté.
2. **Résolution id → nom dans `push_workouts`** : le brief transmet `ids` sans
   les noms mais exige `slugify(workout_name)`. → `push_workouts` appelle
   `client.get_workouts()` en interne pour construire `id → workoutName`.
   **Conséquence assumée** : un appel API supplémentaire (délai 3 s + risque
   429/401). Repli `workout_{id}` si l'id n'est pas trouvé. Si `get_workouts()`
   échoue, `push_workouts` lève (pré-requis, pas un échec de transfert).
3. **Collision insensible à la casse** (FAT32) : comparaison sur `name.lower()`.
   Mise à jour de l'ensemble `existing` après chaque écriture pour gérer deux
   workouts au même nom dans le même batch.
4. **Statut dérivé** : `success` si 0 échec, `partial` si mixte, `failed` si
   tout échoue. `ids` vide → retour immédiat `SyncResult(0,0,0,[])`, pas de
   log d'historique.
5. **`slugify`** : NFKD + suppression diacritiques (ascii), minuscules,
   espaces→`_` (repliés), suppression non-alnum sauf `_`, **suppression des `_`
   de début/fin** (ajout mineur, évite `_` ou `_.FIT`), tronqué à 40, repli
   `"workout"` si vide.
6. **`logger`** utilisé pour tracer les échecs par workout + un bilan final ;
   `history` pour l'entrée `sync_history` (JSON `{files, errors}`).

### Écarts ADR/brief

| Référence | Écart | Justification |
|-----------|-------|---------------|
| Brief `WorkoutSummary.date: datetime` | `datetime | None` | « Si la date est absente » → None nécessaire |
| Brief « slugify(workout_name) » sans source du nom | résolution via `get_workouts()` interne | signature `ids: list[int]` ne porte pas les noms |
| Brief « suppression des non-alnum (sauf `_`) » | ajout du strip des `_` de début/fin | évite un fichier `_.FIT` sur nom tout-espaces |

---

## Corrections post-revue (commit `c4a5418`)

Deux retours du Directeur de Projet traités (cf. `docs/dev/Epic-2-brief.md`,
section « Correction retour Epic 2 »). Régression : 151 tests verts.

### Retour 1 — Signature de `push_workouts` (corrigé)

- `push_workouts(..., items: list[WorkoutSummary])` remplace `ids: list[int]`.
- Supprime l'appel interne `get_workouts()` : plus d'appel API redondant, plus de
  piège du top 20, plus de failure mode. Le frontend fournit les noms (il les a
  via `fetch_workouts()`).
- **Choix `list[WorkoutSummary]`** (et non `list[tuple[int, str]]`) : typé, porte
  déjà date/type, évite une structure ad hoc. Aligné sur le penchant du reviewer.

### Retour 2 — Filtrage credentials sur `sync_history.details` (corrigé)

- `OperationLogger.redact(details)` appliqué avant `history.log_sync(...)`.
- Cohérence : `operation_logs` (via `log`) et `sync_history.details` sont tous
  deux filtrés. Le store reste stupide (filtre côté service).

### Tests complétés (points mineurs b & c)

- (b) `test_write_fit_failure_records` : `OSError` au niveau de l'écriture USB.
- (c) `test_collision_suffix_increments` : collision `_2` → `_3`.
- `test_details_are_redacted` : email + password masqués dans `details`.

### Dette suivie (non traitée, à planifier)

- Index unique `(file_name, direction, source)` + `INSERT OR IGNORE` sur
  `transferred_files` (migration).
- Désinscription de `on_status_changed`.
- Garde « chemin relatif » dans `WatchFilesystem._resolve` (un `Path` absolu
  écraserait `_root`).
- Officialiser l'écart ADR-006 (déclencheur sur label `GARMIN`) en post-merge.

---

## Journal des étapes

| Étape | Commit | Tests | État |
|-------|--------|-------|------|
| 1 — détection USB | `88e9d20` | 87 verts | ✅ validé |
| 2 — fichiers FIT | `cba31ae` | 99 verts | ✅ validé |
| 3 — store (transfers + history) | `30db015` | 120 verts | ✅ validé |
| 4 — download_workout | `278306a` | 125 verts | ✅ validé |
| 5 — sync/workouts | `1987966` | 148 verts | ✅ livré |
| Retours revue (R1 + R2) | `c4a5418` | 151 verts | ✅ corrigé |

## Epic 2 — Backend terminé ✅

Les 5 étapes sont livrées, testées et committées sur `feat/epic-2-workouts`.

### Bilan global

| Étape | Livrable | Commit | Tests cumulés |
|-------|----------|--------|---------------|
| 1 | `watch/detector.py` | `88e9d20` | 87 |
| 2 | `watch/filesystem.py` | `cba31ae` | 99 |
| 3 | `store/transfers.py` + `store/history.py` | `30db015` | 120 |
| 4 | `garmin/client.py` (download_workout) | `278306a` | 125 |
| 5 | `sync/workouts.py` | `1987966` | **148** |

**Régression finale** : `pytest tests/ -m unit` → **148 passed**. Couverture nouveaux modules **95 %**. Imports `watch.detector` et `sync.workouts` OK. Aucun credential dans les logs (le `OperationLogger` applique son filtre, et nos messages n'en contiennent pas).

### Vérification demandée (champ date) — résolue

Confirmé dans `spike-S2/python-garminconnect` : `get_workouts()` expose `updatedDate`/`createdDate` (format `"2018-07-05T17:34:04.0"`) et `sportType.sportTypeKey`. → Tri sur `updatedDate` (repli `createdDate`), `datetime | None` si absent.

### 3 décisions que je te signale pour la revue finale

1. **Résolution id → nom dans `push_workouts`** — le brief transmet `ids` sans les noms mais exige `slugify(workout_name)`. J'ai donc un appel interne à `get_workouts()` pour construire `id → workoutName`. **Conséquence** : un appel API supplémentaire (délai 3 s, risque 429/401). Repli `workout_{id}` si id inconnu ; lève si la résolution échoue.

2. **`WorkoutSummary.date: datetime | None`** — le brief dit `datetime`, mais « si la date est absente » implique None. Les items sans date sont placés en fin de liste en conservant l'ordre API.

3. **Slugify : suppression des `_` de début/fin** (ajout au-delà des règles du brief) — évite `_.FIT` sur un nom tout-espaces. Tout le reste est conforme (NFKD, minuscules, espaces→`_`, non-alnum supprimés sauf `_`, max 40, fallback `workout`).

### Ce qui reste pour l'Epic 2 (hors périmètre backend)

- L'**UI** (`ui/app.py`, `ui/watch_view.py`) — brief séparé du Developer Frontend, qui s'appuie sur les contrats que j'ai figés.
- Les tests `integration` (montre réelle) et `network` (download réel GC) — jalons **E2**, à planifier avec la montre branchée.