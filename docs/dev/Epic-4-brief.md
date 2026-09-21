# Brief de mission — Epic 4 : Historique & logs

Tu es le Developer Frontend du projet OpenRunner55. Voici ta mission pour
l'Epic 4.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epics 1, 2 et 3 livrés et mergés sur `main`** (248 tests verts). L'auth,
le shell post-auth avec navigation 3 sections, la zone GC workouts, la zone
Montre (activités) sont fonctionnelles et validées en réel sur FR55.

L'Epic 4 ajoute la section **« Logs & Historique »** — actuellement un
placeholder dans le shell. C'est une UI de consultation : historique des
syncs passées + logs d'opérations. L'utilisateur peut voir ce qui a été
transféré, quand, et diagnostiquer les échecs.

## Périmètre (MVP)

Stories concernées :

- **US-4.2** — Consulter l'historique des synchronisations : date, sens,
  nombre de fichiers, statut global. Détail par fichier dépliable.
- **US-4.3** — Consulter les logs d'opération : filtrables par niveau
  (INFO/WARN/ERROR), horodatés, sans credentials.

**US-4.1** (interface native, 3 sections navigables) est déjà couverte par
le shell Epic 2 — la navigation existe, il suffit de remplacer le
placeholder par la vraie vue.

**Hors périmètre MVP** (noté pour plus tard, ne pas implémenter) :

- Export des logs (fichier, presse-papier) → backlog
- Recherche full-text dans les logs → backlog
- Pagination/infinite scroll si > 50 syncs → à surveiller, pas bloquant
- Vue « Compte & Paramètres » → Epic 1 US-1.3, chantier séparé
- Agrégation des entrées `sync_history` (cf. § Point connu ci-dessous)

## Point connu — granularité de l'historique

Les controllers `WorkoutsController` et `ActivitiesController` appellent
`push_workouts`/`push_activities` **par fichier** (pour émettre la
progression). Chaque appel logge une entrée `sync_history`. Résultat : une
sync de 10 fichiers produit 10 entrées « 1/1 » au lieu d'une entrée
agrégée « X/10 ».

**Décision pour cet epic** : on affiche les entrées telles quelles. L'utilisateur
voit toutes les opérations, c'est verbeux mais honnête et fonctionnel. La
correction (agégation côté backend ou côté controller) est un chantier
séparé — noté dans la dette technique, à traiter ultérieurement. Ne pas
le corriger dans cet epic.

## Ce qui existe déjà

### Backend (stores Core — figés, non modifiés)

Les stores existent depuis l'Epic 1 et sont peuplés à chaque sync :

- **`store/history.py`** — `SyncHistoryStore` :
  - `get_history(limit=50) -> list[SyncRecord]` — dernières syncs, plus
    récentes d'abord.
  - `SyncRecord` : `id, timestamp, direction, file_count, status, details`.
  - `direction` : `"up"` (Montre → GC) ou `"down"` (GC → Montre).
  - `file_count` : nombre de fichiers réussis (pas le total).
  - `status` : `"success"` | `"partial"` | `"failed"`.
  - `details` : JSON libre, format dépend du service appelant (voir ci-dessous).

- **`store/logger.py`** — `OperationLogger` :
  - `get_logs(limit=100, level=None, operation=None) -> list[LogRecord]`.
  - `LogRecord` : `id, timestamp, operation, level, message`.
  - `level` : `"DEBUG"` | `"INFO"` | `"WARN"` | `"ERROR"`.
  - Filtre anti-credentials appliqué à l'écriture (jamais de mot de passe
    ou email en base — conformité ENF-4).

### Format du champ `details` (JSON)

Dépend du service appelant. À parser côté vue pour l'affichage du détail :

- **`push_workouts`** (direction `"down"`) :
  ```json
  {"files": ["vma.fit", "10k_08.fit"], "errors": ["workout 123: RuntimeError: ..."]}
  ```
- **`push_activities`** (direction `"up"`) :
  ```json
  {"files": ["2026-08-07-08-29-33.fit"], "errors": ["file Activity/ko.fit: ..."], "skipped": 1}
  ```

Le champ `file_count` donne le nombre de succès. Pour afficher un ratio
« X/Y », calculer `Y = file_count + len(errors) + skipped` (si présent).

### Shell UI (existant)

`ui/app.py` contient le shell post-auth avec `Adw.NavigationSplitView` :
3 sections (Activité, Logs & Historique, Compte & Paramètres). La section
« Logs & Historique » est un placeholder (`_build_section_placeholder`).
L'instance de `SyncHistoryStore` et `OperationLogger` sont déjà construites
dans la composition root (`_show_main_view`) — il faut les passer à la
nouvelle vue.

## Ce qu'il faut créer

### 1. `sync/history.py` (nouveau — Service)

L'UX design (§9) impose que l'UI accède à l'historique et aux logs
**uniquement via un Service** — jamais directement via `store/`. Ce
service est un wrapper fin en lecture autour des stores existants.

```python
from openrunner55.store.history import SyncHistoryStore, SyncRecord
from openrunner55.store.logger import OperationLogger, LogRecord


class HistoryService:
    """Service de consultation de l'historique et des logs (ADR-002).

    Interface en lecture seule pour l'UI. Wrappe les stores Core
    (SyncHistoryStore, OperationLogger) sans ajouter de logique métier.
    """

    def __init__(self, history: SyncHistoryStore, logger: OperationLogger) -> None:
        self._history = history
        self._logger = logger

    def get_sync_history(self, limit: int = 50) -> list[SyncRecord]:
        """Retourne les dernières syncs, de la plus récente à la plus ancienne."""
        return self._history.get_history(limit)

    def get_operation_logs(
        self,
        limit: int = 100,
        level: str | None = None,
    ) -> list[LogRecord]:
        """Retourne les logs, filtrables par niveau (INFO/WARN/ERROR)."""
        return self._logger.get_logs(limit=limit, level=level)
```

### 2. `ui/history_controller.py` (nouveau — logique de présentation)

Logique testable sans GTK. Pas d'import de `gi.repository`. Pattern miroir
de `WorkoutsController` / `ActivitiesController`.

Le controller expose l'état (historique, logs, filtre actif) et des
actions (rafraîchir, filtrer par niveau). La vue s'abonne via callbacks.

```python
class HistoryController:
    """Logique de présentation de la section Logs & Historique (sans GTK).

    Pas de dépendance GTK — testable unitairement avec des mocks.
    """

    def __init__(self, service: HistoryService) -> None: ...

    # -- état --
    @property
    def records(self) -> list[SyncRecord]: ...
    @property
    def logs(self) -> list[LogRecord]: ...
    @property
    def log_level_filter(self) -> str | None: ...  # None = tous niveaux

    # -- actions --
    def refresh(self) -> None: ...
        # Recharge l'historique et les logs depuis le service.
        # Notifie la vue via on_records_changed / on_logs_changed.

    def set_log_level_filter(self, level: str | None) -> None: ...
        # None = tous, "INFO"/"WARN"/"ERROR" = filtre.
        # Recharge les logs filtrés et notifie.

    # -- callbacks de la vue --
    def on_records_changed(self, callback: Callable[[], None]) -> None: ...
    def on_logs_changed(self, callback: Callable[[], None]) -> None: ...
```

**Note** : pas de threading. Les lectures SQLite sont instantanées (50-100
lignes, `check_same_thread=False`). Le `refresh()` est synchrone. Si une
latence apparaît avec de gros volumes, on threadera plus tard.

### 3. `ui/history_view.py` (nouveau — vue GTK)

Vue de la section « Logs & Historique ». Layout conforme
`docs/conception/ux-design.md` §4.2 :

- **Vue unique plein contenu** (pas de split).
- **Deux zones superposées** : tableau d'historique (haut) + logs (bas),
  séparées par un séparateur ou un `Gtk.Paned` vertical.

**Tableau d'historique** (haut) :

- `Gtk.ListBox` (une ligne par `SyncRecord`), tri plus récent en haut
  (déjà garanti par `get_history`).
- Chaque ligne affiche :
  - **Date** : `timestamp` formaté `dd/mm/yyyy HH:MM`.
  - **Direction** : `↓` (down, GC → Montre) ou `↑` (up, Montre → GC).
  - **Fichiers** : ratio `file_count / total` (total calculé depuis
    `details` si présent, sinon `file_count`).
  - **Statut** : icône + texte — ✓ Succès (vert), ⚠ Partiel (orange),
    ✗ Échec (rouge).
- **Ligne cliquable → expand** : un `Gtk.Expander` ou un `Gtk.Revealer`
  qui affiche le détail parsé depuis `details` (JSON) :
  - Liste des fichiers réussis (✓ nom)
  - Liste des erreurs (✗ message)
  - Nombre de skippés si présent
- État vide : message « Aucune synchronisation enregistrée ».

**Logs bruts** (bas) :

- `Gtk.ListBox` ou `Gtk.TextView` en lecture seule, scrollable.
- Chaque ligne : `[timestamp] [LEVEL] message` — texte monospace
  (`add_css_class("monospace")`).
- **Filtre par niveau** : 3 `Gtk.ToggleButton` (INFO, WARN, ERROR) +
  « Tous ». Un seul actif à la fois. Le filtre appelle
  `controller.set_log_level_filter()`.
- Couleur du niveau : INFO (normal), WARN (orange), ERROR (rouge) — via
  classes CSS `warning` / `error` sur le label de niveau.
- État vide : message « Aucun log ».

### 4. `ui/app.py` (existant — à étendre)

Remplacer le placeholder « Logs & Historique » par la vraie vue :

- Construire `HistoryService(history, logger)` dans la composition root
  (les instances `history` et `logger` existent déjà).
- Construire `HistoryController(service)`.
- Construire `HistoryView(controller)`.
- Remplacer `self._build_section_placeholder("Logs & Historique")` par la
  vue dans le `Gtk.Stack`.
- Appeler `controller.refresh()` après construction pour le chargement
  initial.

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- L'UI appelle uniquement les Services (`sync/`). Jamais `store/`
  directement. Le service `sync/history.py` est la seule interface.
- L'UI n'importe jamais `garminconnect` directement.
- L'UI ne réimplémente aucune logique métier : pas de parsing JSON complexe
  côté vue (le controller peut parser `details` pour l'affichage — c'est
  de la logique de présentation, pas métier).

### Tests UI (figé)

La logique de présentation (état de l'historique, filtre des logs, calcul
du ratio, parsing du `details`) est extraite dans
`ui/history_controller.py`, une classe **sans dépendance GTK**. Les widgets
GTK restent minces dans `history_view.py` et délèguent au controller.

Les tests unitaires portent sur le controller. Pas de tests d'intégration
GTK dans cet epic (couverture UI cible > 60 %, ADR-008).

## Contrats backend figés

### `store/history.py` — `SyncHistoryStore` (existant, non modifié)

```python
@dataclass(frozen=True)
class SyncRecord:
    id: int
    timestamp: str          # "2026-09-20 18:55:16" (format SQLite datetime)
    direction: str          # "up" | "down" | "both"
    file_count: int         # nombre de fichiers réussis
    status: str             # "success" | "partial" | "failed"
    details: str | None     # JSON libre (voir § Format du champ details)

class SyncHistoryStore:
    def get_history(self, limit: int = 50) -> list[SyncRecord]: ...
```

### `store/logger.py` — `OperationLogger` (existant, non modifié)

```python
@dataclass(frozen=True)
class LogRecord:
    id: int
    timestamp: str          # "2026-09-20 18:55:16"
    operation: str          # ex: "auth.login", "sync.workouts", "sync.activities"
    level: str              # "DEBUG" | "INFO" | "WARN" | "ERROR"
    message: str            # message filtré (anti-credentials)

class OperationLogger:
    def get_logs(
        self,
        limit: int = 100,
        level: str | None = None,       # "DEBUG" | "INFO" | "WARN" | "ERROR" | None
        operation: str | None = None,
    ) -> list[LogRecord]: ...
```

### `sync/history.py` — `HistoryService` (nouveau, à créer)

```python
class HistoryService:
    def __init__(self, history: SyncHistoryStore, logger: OperationLogger) -> None: ...
    def get_sync_history(self, limit: int = 50) -> list[SyncRecord]: ...
    def get_operation_logs(self, limit: int = 100, level: str | None = None) -> list[LogRecord]: ...
```

## Fichiers à créer ou étendre

| Fichier | Action | Description |
|---------|--------|-------------|
| `src/openrunner55/sync/history.py` | Créer | Service `HistoryService` (wrapper fin en lecture) |
| `src/openrunner55/ui/history_controller.py` | Créer | Logique de présentation sans GTK |
| `src/openrunner55/ui/history_view.py` | Créer | Vue GTK de la section Logs & Historique |
| `src/openrunner55/ui/app.py` | Étendre | Wiring du service + controller + vue, remplacement du placeholder |
| `tests/unit/test_history_service.py` | Créer | Tests du service `HistoryService` |
| `tests/unit/test_history_controller.py` | Créer | Tests du controller `HistoryController` |

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

### `tests/unit/test_history_service.py`

- `get_sync_history` délègue à `SyncHistoryStore.get_history` (mock).
- `get_operation_logs` délègue à `OperationLogger.get_logs` (mock).
- Le filtre `level` est transmis au store.

### `tests/unit/test_history_controller.py`

- **Refresh** : `refresh()` charge les records et les logs depuis le
  service ; callbacks `on_records_changed` / `on_logs_changed` déclenchés.
- **Filtre niveau** : `set_log_level_filter("ERROR")` recharge les logs
  filtrés ; callback `on_logs_changed` déclenché.
- **Filtre None** : `set_log_level_filter(None)` recharge tous les logs.
- **Parsing details** : le controller expose une méthode utilitaire pour
  parser le JSON `details` et calculer le ratio (réussis/total). Tester
  avec les deux formats (workouts sans `skipped`, activities avec
  `skipped`).
- **Details malformé** : si le JSON est invalide ou `None`, le controller
  ne lève pas — il retourne un ratio `file_count / file_count` et un
  détail vide.
- **État initial** : `records` et `logs` vides avant `refresh()`.

### Commande

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (248 existants + nouveaux service + controller).

## Critères de done

- `sync/history.py` créé : `HistoryService` wrapper fin.
- `ui/history_controller.py` créé : logique sans GTK.
- `ui/history_view.py` créé : tableau d'historique + logs filtrables.
- `ui/app.py` étendu : placeholder remplacé par la vraie vue, wiring OK.
- `tests/unit/test_history_service.py` créé.
- `tests/unit/test_history_controller.py` créé.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.ui.history_view` ne lève pas d'erreur.
- L'UI n'appelle jamais `store/` directement (passe par `sync/history.py`).
- L'UI n'importe jamais `garminconnect` directement.
- Aucun mot de passe ou token dans les logs ou l'UI (déjà garanti par le
  store, l'UI ne fait qu'afficher).
- Pas de TODO non résolu dans le code livré.

## Ordre de construction — étapes avec validation

Chaque étape = un checkpoint. Tests verts + commit + validation du
Directeur de Projet avant de passer à la suivante.

| Étape | Fichiers | Dépendances |
|-------|----------|-------------|
| **1** | `sync/history.py` + `tests/unit/test_history_service.py` | Stores existants (figés) |
| **2** | `ui/history_controller.py` + `tests/unit/test_history_controller.py` | `sync/history.py` (étape 1) |
| **3** | `ui/history_view.py` (tableau + logs + filtre) + wiring `app.py` | Étapes 1-2 |

À la fin de l'étape 3, la batterie complète `pytest tests/ -m unit -v` doit
passer. Le Directeur de Projet valide then merge.

## Branche

`feat/epic-4-history`. Commits fréquents avec messages conventionnels
(`feat:`, `test:`, `chore:`). Un commit par étape minimum.

## Références dans le repo

- `docs/decisions/adr-002.md` — architecture 3 couches
- `docs/decisions/adr-008.md` — stratégie de tests
- `docs/conception/ux-design.md` §4.2 — wireframe section Logs & Historique
- `docs/dev/Epic-2-brief-frontend.md` — brief frontend de référence (pattern)
- `docs/dev/Epic-2-notes-frontend.md` — notes de dev frontend (choix, écarts)
- `docs/dev/Epic-3-brief-frontend.md` — brief frontend de référence (pattern)
- `docs/dev/Epic-3-notes-frontend.md` — notes de dev frontend (choix, écarts)
- `src/openrunner55/store/history.py` — `SyncHistoryStore` (store existant)
- `src/openrunner55/store/logger.py` — `OperationLogger` (store existant)
- `src/openrunner55/ui/app.py` — shell existant (navigation, composition root)
- `src/openrunner55/ui/workouts_controller.py` — controller de référence (pattern)
- `src/openrunner55/ui/activities_controller.py` — controller de référence (pattern)
- `docs/branching-rules.md` — règles de branches
