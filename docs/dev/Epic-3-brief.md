# Brief de mission — Epic 3 : Activités & métriques Montre → Garmin Connect (Backend)

Tu es le Developer Backend du projet OpenRunner55. Voici ta mission pour
l'Epic 3 backend.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epics 1 et 2 livrés et mergés sur `main`** (179 tests verts). L'auth, le
shell post-auth, la navigation, la zone GC workouts (liste, sélection, envoi
vers la montre) et la détection USB sont en place.

L'Epic 3 ajoute le sens **Montre → Garmin Connect** : lecture des fichiers
.FIT sur la montre, filtrage, téléversement via l'API GC, traçabilité en base.

## Périmètre (MVP)

Stories concernées :

- **US-3.1** — Lister les fichiers .FIT présents sur la montre (type, date,
  taille), avec séparation visuelle des natifs (activités, métriques) vs
  importés (workouts)
- **US-3.2** — Filtrer les fichiers exploitables par GC (exclure les
  non-supportés, liste des exclus consultable, règles documentées)
- **US-3.3** — Synchroniser vers GC : upload des fichiers filtrés, résultat
  par fichier (succès/échec), échec partiel géré

**Hors périmètre MVP** (noté pour plus tard, ne pas implémenter) :

- UI de la zone Montre (liste des fichiers, bouton « Synchroniser vers GC »)
  → brief frontend séparé après figement des contrats
- Décodage FIT avancé (`fit/decoder.py`) → pas nécessaire au MVP, la
  classification se fait par dossier (cf. « Décisions de cadrage »)
- Données HRV → le spike S2 a montré que `get_hrv_data` reste vide après
  upload (endpoint non peuplé). Noté pour investigation post-MVP.
- Retry 429 avancé avec backoff visible → Epic 5 (Should)

## Décisions de cadrage (à valider par le DP)

### 1. Un seul service `sync/activities.py` pour les 4 catégories

L'ADR-002 prévoit `sync/activities.py` (Activity/) et `sync/wellness.py`
(Monitor/Sleep/Metrics/) séparés. Le flux est identique pour les 4 :
`list_fit_files` → `read_fit` → `upload_activity` → `mark_transferred` →
`log_sync`. La seule différence est la catégorie. L'ADR-002 note
explicitement : « le découpage de `sync/` en 3 modules pourrait être fusionné
en un seul si trop fin ». Un seul service réduit le code et la complexité pour
le MVP.

### 2. Déduplication activée

Skip des fichiers déjà uploadés via
`is_transferred(file_name, "up", source)`. Évite les uploads inutiles et les
appels API (délai inter-requêtes 3s, ADR-007). Contrairement à l'Epic 2 où
`push_workouts` ne skippe pas les déjà-transférés (ré-envoi volontaire pour
les workouts), la remontée Montre → GC n'a pas de raison de re-uploader un
fichier identique — GC le gérerait mais on gaspillerait 3s par fichier.

### 3. Pas de `fit/decoder.py` pour le MVP

La classification se fait par dossier (Activity/, Monitor/, Sleep/, Metrics/),
pas par décodage du contenu FIT. Le spike S2 a validé que `upload_activity()`
accepte les FIT natifs sans besoin de les décoder. Le module `fit/decoder.py`
prévu par l'ADR-002 sera ajouté si un besoin de filtrage fin émerge (ex.
distinguer les types d'activités dans Activity/).

## Périmètre de ce brief — Backend uniquement

Tu livres la **couche Core + Services**. Tu ne modifies pas l'UI (figée).

- Extension `garmin/client.py` : ajout de `upload_activity`
- Création `sync/activities.py` : service de remontée Montre → GC
- Tests unitaires pour le service et l'extension `GarminClient`

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- Le Service `sync/activities.py` appelle le Core (`garmin/client.py`,
  `watch/filesystem.py`, `store/*`) et expose une interface simple à l'UI.
- Le Service ne réimplémente aucune logique Core : pas de lecture directe du
  système de fichiers, pas d'appel `garminconnect` direct. Tout passe par
  `GarminClient` et `WatchFilesystem`.
- Le Core ne connaît pas le Service : pas d'import de `sync/` dans
  `garmin/`, `watch/`, `store/`.

### Threading (figé, option A)

Comme pour l'Epic 2, les uploads s'exécuteront dans un thread worker (hors
thread GTK). Le fix SQLite cross-thread (`check_same_thread=False`, ADR-005
révisé) est en place sur `main` — les écritures SQLite depuis le worker
fonctionnent.

Le service `sync/activities.py` est synchrone (pas de threading interne). 
C'est l'UI qui lancera le thread et marshallera les callbacks via
`GLib.idle_add` (comme `WorkoutsController` le fait pour l'Epic 2).

## Contrats backend à figer

Ces signatures sont le contrat sur lequel le frontend s'appuiera. Elles ne
bougeront pas.

### `garmin/client.py` — extension `GarminClient`

```python
def upload_activity(self, file_path: str | Path) -> dict:
    """Téléverse un fichier .FIT vers Garmin Connect.

    Hérite du délai inter-requêtes, du retry 429 et du re-login 401 via
    `_call()` (ADR-007). Référence : `spike-S2/bloc3_upload_activity.py`
    (`garmin.upload_activity(path)` retourne un dict avec
    `detailedImportResult`).

    :param file_path: chemin absolu du fichier .FIT à uploader.
    :returns: réponse API GC (dict). Contient `detailedImportResult` avec
        `successes` et `failures`.
    :raises GarminConnectTooManyRequestsError: si 429 persistant après retries.
    :raises GarminAuthError: si session expirée et reprise impossible.
    """
```

**Point d'attention contrat** : `upload_activity` reçoit un chemin de fichier
(absolu, pas un `Path` relatif à GARMIN/). Le service `sync/activities.py`
doit résoudre le chemin absolu avant l'appel (via `WatchFilesystem` qui connaît
le point de montage).

**Note** : `garminconnect.Garmin.upload_activity(path)` accepte un chemin de
fichier. Le wrapper `_call("upload_activity", path)` passe le chemin tel quel.
La lib gère la lecture du fichier et l'upload HTTP.

### `sync/activities.py` — nouveau service

```python
from dataclasses import dataclass

@dataclass
class UploadableFile:
    """Un fichier .FIT sur la montre, candidat à l'upload vers GC."""
    path: Path           # chemin relatif à GARMIN/ (ex. "Activity/2026-08-07-08-29-33.fit")
    category: str        # "activity" | "monitor" | "sleep" | "metrics"
    size: int            # taille en octets
    already_transferred: bool  # True si déjà uploadé (dédup locale)

@dataclass
class SyncResult:
    """Bilan d'une opération `push_activities` (réutilise le pattern de l'Epic 2)."""
    total: int
    success: int
    failed: int
    errors: list[str]   # un message par fichier échoué
    skipped: int        # fichiers ignorés (déjà transférés)

# Catégories de fichiers .FIT exploitables par GC (spike S2).
# SUMMARY/ est exclu (rejeté 406 par GC).
UPLOADABLE_CATEGORIES = ("Activity", "Monitor", "Sleep", "Metrics")

# Catégories exclues (non uploadables ou non pertinentes).
EXCLUDED_CATEGORIES = ("SUMMARY",)

def list_uploadable_files(
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
) -> list[UploadableFile]:
    """Liste les fichiers .FIT uploadables sur la montre, avec statut de dédup.

    Parcourt les dossiers `UPLOADABLE_CATEGORIES` via
    `watch.list_fit_files(category)`, détermine le statut `already_transferred`
    via `transfers.is_transferred(file_name, "up", source)`.

    Tri : par catégorie puis par nom de fichier (chronologique pour Activity/).
    """

def push_activities(
    client: GarminClient,
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
    history: SyncHistoryStore,
    logger: OperationLogger,
    items: list[UploadableFile],
) -> SyncResult:
    """Upload les fichiers sélectionnés vers Garmin Connect.

    Par fichier : résout le chemin absolu → `client.upload_activity(path)` →
    `transfers.mark_transferred(file_name, "up", source)` en cas de succès.
    En cas d'échec d'un fichier, on continue au suivant (l'erreur est collectée).
    En fin d'opération, une entrée est ajoutée à l'historique des syncs.

    Les fichiers `already_transferred=True` sont skipés (pas d'appel API).
    """
```

**Points d'attention contrat** :

- `list_uploadable_files` retourne des `UploadableFile` avec le chemin
  **relatif à GARMIN/** (convention `WatchFilesystem`). Le frontend dispose
  déjà de la liste — il transmet les `UploadableFile` sélectionnés à
  `push_activities`.
- `push_activities` reçoit `items: list[UploadableFile]` (pas juste des
  chemins). Le frontend a déjà appelé `list_uploadable_files` pour afficher la
  liste — pas de re-listing.
- `push_activities` skippe les `already_transferred=True` (dédup). Le compte
  `skipped` est dans le `SyncResult`.
- `SyncResult.errors` : chaînes préformatées `"file {path}: {ExcType}: {msg}"`,
  à afficher telles quelles dans le résumé d'échec (comme l'Epic 2).
- `source` pour `mark_transferred` / `is_transferred` : dérivé de la catégorie
  (`"activity"`, `"monitor"`, `"sleep"`, `"metrics"` — déjà dans
  `VALID_SOURCES` du store).

### `watch/filesystem.py` — `WatchFilesystem` (existant, non modifié)

```python
class WatchFilesystem:
    def list_fit_files(self, category: str) -> list[Path]  # déjà en place
    def read_fit(self, path: Path) -> bytes                # déjà en place
```

`list_fit_files` retourne des chemins relatifs à GARMIN/. `read_fit` lit les
bytes. Le service `sync/activities.py` utilise ces deux méthodes.

**Note** : `push_activities` ne lit pas les bytes lui-même — il passe le chemin
absolu à `client.upload_activity(path)` qui gère la lecture. Le chemin absolu
est construit via `watch._root / path` (ou une méthode utilitaire à ajouter si
besoin — mais `_root` est privé, donc préférer `read_fit` + écriture temporaire
si `upload_activity` n'accepte que des chemins de fichiers).

**Alternative** : si `garminconnect.Garmin.upload_activity` accepte des bytes
en plus des chemins, on peut utiliser `watch.read_fit(path)` et passer les
bytes. À vérifier au début du dev — si la lib n'accepte que des chemins, il
faudra soit exposer un resolveur de chemin absolu sur `WatchFilesystem`, soit
écrire les bytes dans un fichier temporaire.

### `store/transfers.py` — `TransferredFilesStore` (existant, non modifié)

```python
def mark_transferred(self, file_name: str, direction: str, source: str) -> None
def is_transferred(self, file_name: str, direction: str, source: str | None = None) -> bool
```

`direction="up"`, `source` dérivé de la catégorie. Déjà en place depuis l'Epic 2.

### `store/history.py` — `SyncHistoryStore` (existant, non modifié)

```python
def log_sync(self, direction: str, file_count: int, status: str, details: str | None = None) -> None
```

`direction="up"`, `status` = `"success"` / `"partial"` / `"failed"`. Déjà en
place.

## Fichiers à créer ou étendre

### `garmin/client.py` (existant — à étendre)

Ajouter la méthode `upload_activity(self, file_path) -> dict`. Hérite de
`_call()` pour le délai inter-requêtes, le retry 429 et le re-login 401.

### `sync/activities.py` (nouveau)

Service de remontée Montre → GC. Implémente `list_uploadable_files` et
`push_activities` selon les contrats ci-dessus.

### `sync/__init__.py` (existant)

Rien à faire.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

### Fichier de test à créer

- `tests/unit/test_sync_activities.py` — `list_uploadable_files` et
  `push_activities` avec `GarminClient`, `WatchFilesystem`,
  `TransferredFilesStore`, `SyncHistoryStore`, `OperationLogger` mockés.

### À tester

- **`list_uploadable_files`** :
  - Parcourt les 4 catégories uploadables.
  - Exclut `SUMMARY/` (pas listé).
  - `already_transferred` est True pour les fichiers déjà dans `transfers`.
  - Tri par catégorie puis par nom.
  - Retourne `[]` si la montre est vide.
- **`push_activities`** :
  - Upload les fichiers sélectionnés via `client.upload_activity`.
  - Marque les réussis via `transfers.mark_transferred(file_name, "up", source)`.
  - Skip les `already_transferred=True` (pas d'appel API).
  - Continue au suivant en cas d'échec (erreur collectée dans `errors`).
  - `SyncResult` agrégé correct (total, success, failed, errors, skipped).
  - `log_sync` appelé en fin avec `direction="up"` et le bon `status`.
  - `logger.log` appelé pour les échecs.
- **`upload_activity` (GarminClient)** :
  - Passe le chemin à `_call("upload_activity", path)`.
  - Hérite du délai inter-requêtes et du retry 429 (déjà testé pour
    `download_workout` — pas besoin de re-tester, juste vérifier que la
    méthode expose bien le contrat).

### Commande

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (179 existants + nouveaux). Les tests d'intégration
(upload réel vers GC) sont pour le jalon E4, pas pour cette session.

## Critères de done (backend)

- `garmin/client.py` étendu : méthode `upload_activity` ajoutée.
- `sync/activities.py` créé : `list_uploadable_files` + `push_activities`.
- `tests/unit/test_sync_activities.py` créé : tests du service.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.sync.activities` ne lève pas d'erreur.
- Aucun appel réseau sur le thread GTK (le service est synchrone, c'est l'UI
  qui gérera le threading).
- Aucun mot de passe ou token dans les logs.
- Le Service n'importe jamais `garminconnect` directement (passe par
  `GarminClient`).
- Pas de TODO non résolu dans le code livré.

## Ordre de construction — étapes avec validation

Chaque étape = un checkpoint. Tests verts + commit + validation du Directeur
de Projet avant de passer à la suivante.

| Étape | Fichiers | Dépendances |
|-------|----------|-------------|
| **1** | `garmin/client.py` (ajout `upload_activity`) | `garminconnect` (existant) |
| **2** | `sync/activities.py` (`list_uploadable_files`) + tests | `watch/filesystem.py`, `store/transfers.py` (existants) |
| **3** | `sync/activities.py` (`push_activities`) + tests | étape 1-2, `store/history.py`, `store/logger.py` (existants) |

À la fin de l'étape 3, la batterie complète `pytest tests/ -m unit -v` doit
passer. Le Directeur de Projet valide then merge.

## Branche

`feat/epic-3-activities`. Commits fréquents avec messages conventionnels
(`feat:`, `test:`, `chore:`). Un commit par étape minimum.

## Références dans le repo

- `docs/decisions/adr-002.md` — architecture 3 couches, interfaces publiques
- `docs/decisions/adr-005.md` — SQLite + `check_same_thread=False` (révisé E3)
- `docs/decisions/adr-007.md` — retry/backoff 429, délai inter-requêtes
- `docs/decisions/adr-008.md` — stratégie de tests
- `docs/exploration/spike-S2-resultat.md` — pipeline bidirectionnel validé
- `docs/exploration/tree-FR55.md` — arborescence des fichiers de la montre
- `docs/cadrage/epics.md` — US-3.1, US-3.2, US-3.3
- `docs/dev/Epic-2-brief.md` — référence de brief (pattern à suivre)
- `docs/dev/Epic-2-notes-backend.md` — notes de dev backend (choix, écarts)
- `src/openrunner55/garmin/client.py` — wrapper à étendre
- `src/openrunner55/watch/filesystem.py` — `WatchFilesystem` (non modifié)
- `src/openrunner55/store/transfers.py` — `TransferredFilesStore` (non modifié)
- `src/openrunner55/store/history.py` — `SyncHistoryStore` (non modifié)
- `src/openrunner55/store/logger.py` — `OperationLogger` (non modifié)
- `src/openrunner55/sync/workouts.py` — référence d'implémentation (pattern)
- `docs/branching-rules.md` — règles de branches
