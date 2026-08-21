# Notes de dev backend — Epic 3 (Activités & métriques Montre → Garmin Connect)

> Document vivant. Consigne les choix, écarts et observations du Developer
> Backend au fil des étapes de l'Epic 3. Source de vérité pour la revue du
> Directeur de Projet ; complète le brief (`Epic-3-brief.md`) sans le dupliquer.
>
> Branche : `feat/epic-3-activities`.

## Environnement (observations initiales)

| Point | Constat | Conséquence |
|-------|---------|-------------|
| Baseline tests | **179 tests verts** (`pytest tests/ -m unit`) avant tout changement | Point de référence pour la régression |
| Python | 3.14.6 (venv `.venv`) | `requires-python >=3.12` → OK |
| `garminconnect` | 0.3.9 (dans le venv) | Source lue directement dans `spike-S2/python-garminconnect` pour confirmer la signature |
| Branche | `feat/epic-3-activities` créée depuis `main` (2 commits d'avance non poussés) | — |

---

## Découverte clé de début de dev — signature `upload_activity`

**Question du brief (ligne 19) résolue par lecture du code source de la lib**
(`spike-S2/python-garminconnect/garminconnect/__init__.py`, ligne 2413) :

```python
def upload_activity(self, activity_path: str) -> Any:
    if not activity_path:
        raise ValueError("activity_path cannot be empty")
    if not isinstance(activity_path, str):
        raise ValueError("activity_path must be a string")
    ...
```

**Conclusion : `upload_activity` n'accepte QUE un chemin de fichier (`str`),
PAS des bytes.** La lib ouvre le fichier elle-même (`p.open("rb")`) et fait le
POST multipart. → L'option « passer des bytes via `read_fit` » du brief (ligne
230-234) est **éliminée**. Il faut résoudre un **chemin absolu** côté service.

### Conséquence — 2 méthodes à ajouter sur `WatchFilesystem`

Le brief marque `watch/filesystem.py` « existant, non modifié », mais prévoit
explicitement l'écart (lignes 227 et 233 : « exposer un resolveur de chemin
absolu sur WatchFilesystem »). Deux besoins concrets émergent du contrat,
qu'aucune méthode existante ne couvre :

| Besoin | Source du besoin | Méthode proposée |
|--------|------------------|------------------|
| Chemin **absolu** pour `upload_activity` | `_resolve`/`_root` sont privés ; le service ne doit pas toucher au FS | `absolute_path(path: Path) -> Path` |
| **Taille** (`UploadableFile.size`) | `list_fit_files` ne retourne que des `Path` | `file_size(path: Path) -> int` (`stat().st_size`) |

**Justification `file_size` (pas `len(read_fit(path))`)** : `Activity/` peut
contenir 200+ fichiers (~500 Ko chacun) ; lire tout en mémoire pour une taille
serait du gaspillage (≈100 Mo transitoires). `stat().st_size` ne lit pas le
contenu. Le service reste FS-agnostique (aucun `.stat()` direct côté service).

→ **Écart signalé au DP** : 2 méthodes additives sur `WatchFilesystem`
(modification minimale, aucune méthode existante touchée). À valider.

---

## Décisions de conception (à valider par le DP)

### D1 — `file_name` de dédup = basename (`path.name`), pas le chemin complet

`transfers.is_transferred(file_name, "up", source)` / `mark_transferred` :
`file_name` = **nom de fichier seul** (ex. `2026-08-07-08-29-33.fit`), la
`source` (ex. `activity`) portant déjà la catégorie. Cohérent avec l'Epic 2
(`mark_transferred(filename, "down", "workout")` avec basename). La clé de
dédup reste unique : `(basename, "up", source)`.

### D2 — mapping `category` (dossier) → `source` (dédup)

Deux conventions coexistent dans le brief :
- `UPLOADABLE_CATEGORIES = ("Activity", "Monitor", "Sleep", "Metrics")` → noms
  de dossiers FAT32 (capitalisés), passés à `watch.list_fit_files(category)`.
- `UploadableFile.category = "activity" | "monitor" | "sleep" | "metrics"` →
  minuscules, servent aussi de `source` pour la dédup (déjà dans
  `VALID_SOURCES` du store).

→ `category = folder.lower()` ; `source = category`. Aucune table de mapping
nécessaire.

### D3 — `UploadableFile.category` porté en minuscules

Le brief fixe `category: str  # "activity" | "monitor" | "sleep" | "metrics"`
(ligne 144), donc minuscules. C'est le service qui fait `folder.lower()`.

### D4 — Succès = absence d'exception (pas de parsing de `detailedImportResult`)

Le brief (ligne 189, 293) définit l'échec comme une **exception levée** par
`client.upload_activity`, collectée puis on continue au suivant. La réponse
`detailedImportResult.successes/failures` n'est **pas parsée** au MVP : les 4
catégories uploadables sont déjà validées par le spike S2 (SUMMARY/ est exclu
en amont). Cohérent avec le pattern Epic 2 (`download_workout` : exception =
échec). `mark_transferred` est appelé sans `gc_activity_id` (le brief ne
l'exige pas → reste `None`).

### D5 — Statut & `log_sync` (edge cases)

- `items` vide → retour immédiat `SyncResult(0,0,0,[],0)`, **aucun** `log_sync`
  (pattern Epic 2).
- Statut dérivé : `failed == 0` → `success` ; `success > 0 and failed > 0` →
  `partial` ; `success == 0 and failed > 0` → `failed`.
- **Cas « tout skippé »** (`success=0, failed=0, skipped>0`) → statut `success`,
  `file_count = success = 0`. L'opération a bien eu lieu (l'utilisateur a
  déclenché la sync), on trace donc une entrée, sans échec.
- `log_sync("up", success, status, details)` : `file_count` = fichiers
  réellement uploadés (cohérent Epic 2). `details` filtré via
  `OperationLogger.redact(...)` avant persistance (cohérent Epic 2 / ENF-4).

### D6 — Format des erreurs

`SyncResult.errors` : `f"file {item.path}: {type(exc).__name__}: {exc}"`
(`{item.path}` = chemin relatif GARMIN/, comme le brief ligne 207 l'impose —
pas le basename). `logger.log("sync.activities", "error", ...)` par échec.

---

## Plan de développement (étapes avec checkpoint)

Ordre aligné sur le brief (§ « Ordre de construction »), précédé d'une étape
**zéro** rendue nécessaire par la découverte de début de dev.

| Étape | Contenu | Fichiers | Dépendances |
|-------|---------|----------|-------------|
| **0** | Ajout `absolute_path()` + `file_size()` sur `WatchFilesystem` + tests | `watch/filesystem.py`, `tests/unit/test_filesystem.py` | — |
| **1** | Ajout `upload_activity()` sur `GarminClient` + tests | `garmin/client.py`, `tests/unit/test_garmin_client.py` | `garminconnect` |
| **2** | `sync/activities.py` — `list_uploadable_files` + tests | `sync/activities.py`, `tests/unit/test_sync_activities.py` | étape 0, `store/transfers.py` |
| **3** | `sync/activities.py` — `push_activities` + tests + batterie complète | idem | étapes 1-2, `store/history.py`, `store/logger.py` |

À la fin de l'étape 3 : `python -m pytest tests/ -m unit -v` doit passer à
100 % (179 + nouveaux). Un commit par étape (`feat:`/`test:`).

---

## Points à valider par le Directeur de Projet (avant de coder)

1. **Étape 0 (écart « WatchFilesystem non modifié »)** : ajout de
   `absolute_path()` et `file_size()`. Validé ?
2. **D1** — `file_name` = basename (pas chemin complet) pour la dédup. Validé ?
3. **D5** — cas « tout skippé » → `log_sync("up", 0, "success")` (et non pas
   absence de trace). Validé ?
4. **D4** — pas de parsing de `detailedImportResult` au MVP (succès = absence
   d'exception). Validé ?

---

## Journal des étapes

| Étape | Commit | Tests | État |
|-------|--------|-------|------|
| 0 — `WatchFilesystem` (absolute_path + file_size) | `abbf929` | 183 verts | ✅ livré |
| 1 — `GarminClient.upload_activity` | `b77a358` | 189 verts | ✅ livré |
| 2 — `list_uploadable_files` | `353837a` | 196 verts | ✅ livré |
| 3 — `push_activities` | `b0334ea` | 205 verts | ✅ livré |

## Epic 3 — Backend terminé ✅

Les 4 étapes (0 + 1 + 2 + 3) sont livrées, testées et committées sur
`feat/epic-3-activities`.

### Bilan global

| Étape | Livrable | Commit | Tests cumulés |
|-------|----------|--------|---------------|
| 0 | `watch/filesystem.py` (+absolute_path, +file_size) | `abbf929` | 183 |
| 1 | `garmin/client.py` (+upload_activity) | `b77a358` | 189 |
| 2 | `sync/activities.py` (list_uploadable_files) | `353837a` | 196 |
| 3 | `sync/activities.py` (push_activities) | `b0334ea` | **205** |

**Régression finale** : `pytest tests/ -m unit` → **205 passed** (179 + 26
nouveaux). Couverture des 3 modules touchés : **100 %**. Imports
`openrunner55.sync.activities` OK. Le service n'importe jamais `garminconnect`
directement (passe par `GarminClient`). Le Core (garmin/, watch/, store/)
n'importe jamais `sync/` (ADR-002 respecté). Aucun credential dans les logs
(`OperationLogger.redact` appliqué sur `sync_history.details`). Aucun TODO.

### Écarts assumés (tous validés par le DP en amont)

| Référence | Écart | Justification |
|-----------|-------|---------------|
| Brief « `watch/filesystem.py` non modifié » | +2 méthodes additives (`absolute_path`, `file_size`) | Découverte de début de dev : `upload_activity` n'accepte qu'un chemin `str` (pas de bytes) → résolution absolue nécessaire ; `UploadableFile.size` n'avait aucune source sans lecture du contenu. Aucune méthode existante touchée. |
| `file_name` de dédup | = basename (`path.name`), pas le chemin complet | Cohérent Epic 2 ; la `source` porte déjà la catégorie. |
| `log_sync` « tout skippé » | `("up", 0, "success")` (une trace, sans échec) | L'opération a bien eu lieu ; aucun échec à reporter. |
| Succès d'upload | = absence d'exception (`detailedImportResult` non parsé) | Les 4 catégories sont validées par le spike S2 ; SUMMARY/ exclu en amont. |

### Dette non traitée (héritée, hors périmètre Epic 3)

- Garde « chemin relatif » dans `WatchFilesystem._resolve`/`absolute_path` (un
  `Path` absolu écraserait `_root`) — déjà listée en dette Epic 2, toujours
  pertinente.
- Index unique `(file_name, direction, source)` + `INSERT OR IGNORE` sur
  `transferred_files` (migration) — hérité Epic 2.

### Ce qui reste pour l'Epic 3 (hors périmètre backend)

- L'**UI** de la zone Montre (liste des fichiers, bouton « Synchroniser vers
  GC ») — brief séparé du Developer Frontend, qui s'appuie sur les contrats
  figés ici (`list_uploadable_files` → `push_activities`).
- Les tests `integration` (montre réelle) et `network` (upload réel GC) —
  jalon E4.
