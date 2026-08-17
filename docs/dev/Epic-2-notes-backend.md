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

## Points à trancher / vérifier pour les étapes suivantes

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

## Journal des étapes

| Étape | Commit | Tests | État |
|-------|--------|-------|------|
| 1 — détection USB | `88e9d20` | 87 verts | ✅ validé |
| 2 — fichiers FIT | `cba31ae` | 99 verts | ✅ validé |
| 3 — store (transfers + history) | `30db015` | 120 verts | ✅ validé |
| 4 — download_workout | `278306a` | 125 verts | ✅ validé |
