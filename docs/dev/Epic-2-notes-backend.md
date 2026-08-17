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

## Journal des étapes

| Étape | Commit | Tests | État |
|-------|--------|-------|------|
| 1 — détection USB | `88e9d20` | 87 verts | ✅ validé |
