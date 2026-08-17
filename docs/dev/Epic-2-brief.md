# Brief de mission — Epic 2 : Workouts Cloud → Montre (Backend)

Tu es le Developer Backend du projet OpenRunner55. Voici ta mission pour l'Epic 2.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epic 1 (Authentification) est livré et mergé.** L'auth headless fonctionne,
le store SQLite est en place (schéma v2), `garmin/client.py` expose déjà
`get_workouts()` et `get_activities()` avec retry 429 et re-login 401.

L'Epic 2 ajoute le sens **Cloud → Montre** : récupérer les workouts de Garmin
Connect, les télécharger en `.FIT`, et les copier sur la montre FR55 branchée
en USB.

## Périmètre (MVP)

Stories concernées (périmètre fonctionnel, cf. note sur la numérotation) :

- **Lister les workouts GC** triés du plus récent au plus ancien (nom, date, type)
- **Sélection multiple** de workouts via checkboxes
- **Détection USB** de la montre FR55 avant tout transfert
- **Envoi** : téléchargement `.FIT` → copie vers `GARMIN/Workouts/` → confirmation

**Hors périmètre MVP** (noté pour plus tard, ne pas implémenter) :

- Détection des doublons (workouts déjà présents sur la montre) → Should
- Suppression de workouts de la montre → Should
- Bouton « Synchroniser » (remontée Montre → GC) → Epic 3
- Zone « Montre » avec liste des activités → Epic 3

> **Note numérotation US :** `docs/cadrage/epics.md` et `docs/cadrage/mvp.md`
> numérotent différemment les US de l'Epic 2. Le périmètre fonctionnel ci-dessus
> fait foi. Point à aligner dans les docs de cadrage ultérieurement.

## Périmètre de ce brief — Backend uniquement

Tu livrés le **Core** et les **Services**. Tu ne fais **pas** l'UI.

- Core : `watch/`, `store/transfers.py`, `store/history.py`, extension de
  `garmin/client.py`
- Services : `sync/workouts.py`
- Tests unitaires pour chaque module

L'UI (`ui/app.py`, `ui/watch_view.py`) sera réalisée par le Developer Frontend
dans un brief séparé, après validation du backend. Les interfaces publiques
que tu exposes (noms de classes, signatures de méthodes) sont le contrat sur
lequel le frontend s'appuiera — sois rigoureux dessus.

## Modalité de travail — étapes avec validation

Tu travailles sur la branche **`feat/epic-2-workouts`**.

Le développement se fait **par étape** (un fichier ou un bloc cohérent). À la
fin de chaque étape :

1. Les tests unitaires de l'étape passent (`pytest tests/ -m unit -v`)
2. La régression est verte (tous les tests existants passent toujours)
3. Tu commit avec un message conventionnel (`feat:`, `test:`, `chore:`)
4. Tu présentes le livrable au Directeur de Projet (Franck) pour validation
5. **Tu attends le feu vert avant de passer à l'étape suivante**

Pas d'avance sur plusieurs étapes sans validation. Un point de contrôle à
chaque étape = un rollback facile si quelque chose dérape.

L'ordre des étapes est défini en bas de ce brief (section « Ordre de
construction »).

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- L'UI appelle uniquement les Services (`sync/`). Jamais `garmin/`, `watch/`,
  `store/` directement (sauf `sync/history.py` qui est le pont UI → store en
  lecture seule).
- Les Services appellent le Core. `sync/workouts.py` orchestre
  `garmin/client.py` + `watch/filesystem.py` + `store/`.
- `watch/` ne connaît ni Garmin ni la logique de nommage. Il reçoit un chemin
  et écrit des bytes.
- Le slugify (nommage des fichiers workout sur la montre) est responsabilité
  de `sync/workouts.py` (Service), pas de `watch/` (Core).
- `garmin/client.py` hérite du délai inter-requêtes 3s et du retry 429 déjà
  implémentés. `download_workout()` bénéficie du même `_call()` que
  `get_workouts()`.

## Fichiers à créer ou étendre

### Core — extension

#### `garmin/client.py` (existant — à étendre)

Ajouter la méthode :

```python
def download_workout(self, workout_id: int) -> bytes:
    """Télécharge un workout au format .FIT (bytes)."""
    return self._call("download_workout", workout_id)
```

Référence : `spike-S2/bloc5_roundtrip_workout.py` — `garmin.download_workout(workoutId)`
retourne les bytes du FIT. Hérite du délai 3s + retry 429 + re-login 401 via
`_call()`. Aucune logique supplémentaire à ajouter.

### Core — nouveaux modules

#### `watch/__init__.py` (nouveau package)

Vide, juste pour faire du package.

#### `watch/detector.py` — `WatchDetector`

ADR-006. Détection USB de la FR55.

- **pyudev (actif)** : `pyudev.Monitor` sur le sous-système `block`, écoute
  les événements `bind`/`unbind`. Quand un device avec le label `GARMIN` est
  détecté, vérifie la présence de `GarminDevice.xml` pour confirmer la FR55.
- **Polling (fallback)** : toutes les 1s, vérifie si
  `/run/media/$USER/GARMIN/GARMIN/GarminDevice.xml` existe. Coût négligeable,
  filet de sécurité si pyudev manque un événement.
- **Thread séparé** : le Monitor pyudev et le polling tournent dans un thread
  dédié pour ne pas bloquer la boucle GTK. Le signal `on_status_changed` est
  émis thread-safe via `GLib.idle_add()`.
- **Identification FR55** : présence de `GarminDevice.xml` dans `GARMIN/` à la
  racine du volume monté (cf. `docs/exploration/tree-FR55.md`).

Interface publique (ADR-002) — **contrat pour le frontend** :

```python
class WatchDetector:
    def is_connected() -> bool
    def get_mount_path() -> Path | None
    def on_status_changed(callback: Callable[[bool], None])  # signal
```

Démarrage : le détecteur est démarré au lancement de l'app post-auth (côté
frontend). Le polling et le monitor tournent en arrière-plan.

#### `watch/filesystem.py` — `WatchFilesystem`

ADR-002. Lecture/écriture des fichiers FIT sur la montre.

- Chemin base : `{mount_path}/GARMIN/`
- Dossiers gérés : `Activity/`, `Workouts/`, `Monitor/`, `Sleep/`, `Metrics/`
- Pour l'Epic 2 : surtout `write_fit()` vers `Workouts/`

Interface publique (ADR-002) — **contrat pour le frontend** :

```python
class WatchFilesystem:
    def __init__(self, mount_path: Path)
    def list_fit_files(category: str) -> list[Path]   # category ∈ {"Activity","Workouts","Monitor","Sleep","Metrics"}
    def read_fit(path: Path) -> bytes
    def write_fit(path: Path, data: bytes) -> None     # lève OSError si échec
```

`write_fit` crée le dossier parent si nécessaire. **Lève `OSError`** en cas
d'échec (déconnexion USB, permissions) — le service décide de la stratégie
(continuer au suivant vs abort). Ne retourne pas de booléen silencieux.

#### `store/transfers.py` — `TransferredFilesStore`

ADR-005. Déduplication locale via la table `transferred_files` (déjà créée
dans le schéma, cf. `store/database.py`).

```python
class TransferredFilesStore:
    def __init__(self, db: Database)
    def mark_transferred(file_name: str, direction: str, source: str, gc_activity_id: int | None = None) -> None
    def is_transferred(file_name: str, direction: str) -> bool
```

- `direction` ∈ `{"up", "down"}`
- `source` ∈ `{"activity", "monitor", "sleep", "metrics", "workout"}`
- Pour l'Epic 2 : `mark_transferred(slug_filename, "down", "workout")` après
  copie réussie sur la montre.

#### `store/history.py` — `SyncHistoryStore`

ADR-002 / ADR-005. Historique des syncs (table `sync_history` déjà créée).

```python
class SyncHistoryStore:
    def __init__(self, db: Database)
    def log_sync(direction: str, file_count: int, status: str, details: str | None = None) -> None
    def get_history(limit: int = 50) -> list[SyncRecord]
```

- `direction` ∈ `{"up", "down", "both"}`
- `status` ∈ `{"success", "partial", "failed"}`
- `details` : JSON libre (liste des fichiers, erreurs)
- Pour l'Epic 2 : `log_sync("down", N, "success"|"partial"|"failed", ...)`
  après chaque envoi de workouts.

### Service — nouveau module

#### `sync/__init__.py` (nouveau package)

Vide.

#### `sync/workouts.py` — orchestration Cloud → Montre

ADR-002. Cœur métier de l'Epic 2.

```python
@dataclass
class WorkoutSummary:
    workout_id: int
    name: str
    date: datetime | None   # pour le tri récent → ancien ; None si absente
    type: str               # sport / catégorie

@dataclass
class SyncResult:
    total: int
    success: int
    failed: int
    errors: list[str]    # détails par workout échoué

def fetch_workouts(client: GarminClient) -> list[WorkoutSummary]:
    """Récupère et trie les workouts GC (récent → ancien)."""

def push_workouts(
    client: GarminClient,
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
    history: SyncHistoryStore,
    logger: OperationLogger,
    items: list[WorkoutSummary],
) -> SyncResult:
    """Télécharge, slugify, copie sur la montre, trace en base."""
```

> **Note contrat.** `push_workouts` reçoit `items: list[WorkoutSummary]`
> (et non `ids: list[int]`) : le frontend a déjà appelé `fetch_workouts()`
> pour afficher la liste, il dispose donc des noms. Cela évite un appel
> API redondant à `get_workouts()` côté service (délai 3 s, risque 429/401,
> limite top 20). Le service ne rappelle jamais `get_workouts()`.

**Flux `push_workouts`** (par workout de `items`) :

1. `client.download_workout(item.workout_id)` → bytes `.FIT`
2. `slugify(item.name)` → nom de fichier (règles ci-dessous) ; repli
   `workout_{item.workout_id}` si `item.name` est vide
3. Vérification collision : si `{slug}.FIT` existe déjà dans `Workouts/`
   (comparaison insensible à la casse, FAT32), suffixer `_2`, `_3`, etc.
   (via `watch.list_fit_files("Workouts")`)
4. `watch.write_fit(Workouts/{slug}.FIT, bytes)` → copie USB (lève `OSError`)
5. Si succès : `transfers.mark_transferred(slug_filename, "down", "workout")`
6. Si échec (`download_workout` ou `write_fit`) : ajout à `SyncResult.errors`,
   on continue au suivant
7. À la fin : `history.log_sync("down", success, status, details_json)` où
   `details_json` est passé par `OperationLogger.redact()` (cohérence avec
   `operation_logs` — aucun credential persisté). Statut dérivé :
   `success` si 0 échec, `partial` si mixte, `failed` si tout échoué.
   `items` vide → retour immédiat `SyncResult(0,0,0,[])`, pas de `log_sync`.

**Règles de slugify** (ADR-002) :

- Minuscules
- Suppression des accents (normalisation NFKD)
- Espaces → `_`
- Suppression des caractères non alphanumériques (sauf `_`)
- Longueur max 40 caractères avant l'extension
- Le nom affiché par la montre vient du champ `wkt_name` dans le FIT, pas du
  nom de fichier. Le slugify ne concerne que la lisibilité du système de
  fichiers FAT32.

**Tri `fetch_workouts`** : sur le champ date de la réponse API GC, du plus
récent au plus ancien. Si la date est absente, conserver l'ordre de l'API.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

### Fichiers de tests à créer

- `tests/unit/test_detector.py` — `WatchDetector` : logique de détection avec
  pyudev mocké + `os.path.exists` mocké. Vérifie les transitions d'état et
  l'émission du signal.
- `tests/unit/test_filesystem.py` — `WatchFilesystem` : list/read/write sur
  arborescence mockée (`tmp_path` pytest avec dossiers `GARMIN/Workouts/`
  etc.).
- `tests/unit/test_sync_workouts.py` — `fetch_workouts` (tri, extraction
  métadonnées) + `push_workouts` (download → slugify → collision → write →
  mark) avec `GarminClient` et `WatchFilesystem` mockés. Tester le slugify
  exhaustivement (accents, espaces, caractères spéciaux, longueur, collisions).
- `tests/unit/test_transfers.py` — `TransferredFilesStore` : mark/is_transferred
  sur SQLite `:memory:`.
- `tests/unit/test_history.py` — `SyncHistoryStore` : log_sync/get_history sur
  SQLite `:memory:`.

### Fichier de test à étendre

- `tests/unit/test_garmin_client.py` (existant) — ajouter test
  `download_workout()` : vérifie que `_call("download_workout", id)` est
  invoqué avec le bon ID, hérite du délai 3s et du retry 429.

### Commande

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % à chaque étape. Les tests `integration` (montre réelle)
et `network` (download réel GC) sont pour le jalon E2, pas pour la session
de dev.

## Références dans le repo

- `docs/decisions/adr-002.md` — architecture 3 couches, interfaces publiques
- `docs/decisions/adr-005.md` — SQLite, schéma, `transferred_files`
- `docs/decisions/adr-006.md` — détection USB pyudev + polling
- `docs/decisions/adr-007.md` — retry/backoff, délai 3s
- `docs/decisions/adr-008.md` — stratégie de tests
- `docs/conception/ux-design.md` — wireframes, parcours C (référence pour
  comprendre le flux utilisateur, pas à implémenter côté backend)
- `docs/exploration/tree-FR55.md` — arborescence de la montre
- `docs/exploration/spike-S2-resultat.md` — code de référence (bloc 5 roundtrip)
- `spike-S2/bloc5_roundtrip_workout.py` — download_workout + copie USB
- `src/openrunner55/garmin/client.py` — wrapper existant à étendre
- `src/openrunner55/store/database.py` — schéma déjà en place
- `docs/branching-rules.md` — règles de branches

## Critères de done (backend)

- Les 8 fichiers source créés/étendus et propres (pas de TODO non résolu)
- `python -m pytest tests/ -m unit -v` passe à 100 % (tests existants + nouveaux)
- `import openrunner55.watch.detector`, `import openrunner55.sync.workouts`
  ne lèvent pas d'erreur
- Le slugify est testé exhaustivement (accents, espaces, spéciaux, longueur,
  collisions `_2`/`_3`)
- `WatchDetector` est testable sans montre branchée (pyudev mocké)
- `WatchFilesystem` est testable sans montre (tmp_path)
- Aucun mot de passe ou token dans les logs
- Les interfaces publiques correspondent aux signatures du brief (contrat
  pour le Developer Frontend)

## Ordre de construction — étapes avec validation

Chaque étape = un checkpoint. Tests verts + commit + validation du Directeur
de Projet avant de passer à la suivante.

| Étape | Fichiers | Dépendances |
|-------|----------|-------------|
| **1** | `watch/__init__.py` + `watch/detector.py` + `tests/unit/test_detector.py` | pyudev (mockable) |
| **2** | `watch/filesystem.py` + `tests/unit/test_filesystem.py` | tmp_path pytest |
| **3** | `store/transfers.py` + `store/history.py` + `tests/unit/test_transfers.py` + `tests/unit/test_history.py` | `store/database.py` (existant) |
| **4** | `garmin/client.py` (extension `download_workout`) + `tests/unit/test_garmin_client.py` (extension) | `auth/` (existant) |
| **5** | `sync/__init__.py` + `sync/workouts.py` + `tests/unit/test_sync_workouts.py` | garmin + watch + store (étapes 1-4) |

À la fin de l'étape 5, la batterie complète `pytest tests/ -m unit -v` doit
passer (Epic 1 + Epic 2 backend). Le Directeur de Projet valide then merge.

## Branche

`feat/epic-2-workouts`. Commits fréquents avec messages conventionnels
(`feat:`, `test:`, `chore:`). Un commit par étape minimum.

## Corrections post-revue (commit `c4a5418`)

Deux retours du Directeur de Projet traités après la livraison initiale :

1. **Signature `push_workouts`** — reçoit `items: list[WorkoutSummary]` au
   lieu de `ids: list[int]`. Supprime l'appel interne redondant à
   `get_workouts()` (délai 3 s, risque 429/401, piège du top 20). Le
   frontend dispose déjà des noms via `fetch_workouts()`.
2. **Filtrage credentials sur `sync_history.details`** — `details` passé
   par `OperationLogger.redact()` avant `log_sync()` (cohérence avec
   `operation_logs`).

Dette suivie (non bloquante) : index unique `(file_name, direction, source)`
sur `transferred_files`, désinscription callback `on_status_changed`,
garde `_resolve` sur chemin relatif, officialisation de l'écart ADR-006
(déclencheur sur label `GARMIN`).