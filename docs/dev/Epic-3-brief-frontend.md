# Brief de mission — Epic 3 : Activités Montre → Garmin Connect (Frontend)

Tu es le Developer Frontend du projet OpenRunner55. Voici ta mission pour
l'Epic 3 frontend.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epics 1 et 2 livrés et mergés sur `main`** (205 tests verts). L'auth, le
shell post-auth avec navigation 3 sections, la zone GC workouts (liste,
sélection, envoi vers la montre), la détection USB et le fix SQLite
cross-thread sont en place.

**Epic 3 backend livré et mergé.** Les contrats backend sont figés (cf.
section « Contrats backend figés » ci-dessous). Le frontend s'y appuie.

L'Epic 3 frontend ajoute l'UI du sens **Montre → Garmin Connect** : la zone
Montre (placeholder dans l'Epic 2) devient fonctionnelle — liste des fichiers
.FIT uploadables, sélection, bouton « Synchroniser vers GC ».

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

- Décodage FIT avancé (type d'activité, métriques détaillées) → `fit/decoder.py`
  ajourné (ADR-002)
- Retry 429 avancé avec backoff visible → Epic 5 (Should)
- Notifications desktop → Epic 5 (Could)
- Pagination de la liste des fichiers (si > 200 fichiers) → à surveiller, pas
  bloquant au MVP

## Décision de cadrage — UX de la « première sync »

**Contexte** : l'utilisateur a potentiellement 200+ fichiers .FIT sur la
montre, dont la plupart sont déjà sur GC (via Garmin Express). Il faut guider
l'upload pour éviter un déluge de requêtes inutiles.

**Décision** : le backend fournit déjà le drapeau `already_transferred` sur
chaque `UploadableFile` (via `transfers.is_transferred`). L'UX s'appuie dessus :

1. **Affichage du statut** : chaque ligne indique visuellement si le fichier
   est déjà transféré (icône ou libellé grisé) ou nouveau (libellé normal).
2. **Pré-sélection par défaut** : seuls les `already_transferred=False` sont
   cochés à l'affichage de la liste. L'utilisateur peut décocher.
3. **Bouton « Tout sélectionner »** : disponible, permet de forcer la
   sélection y compris les déjà transférés. Les fichiers `already_transferred`
   seront skippés par `push_activities` sans appel API (délai 3s évité).
4. **Cas limite — première utilisation** : store SQLite vide → tous les
   fichiers apparaissent comme non transférés. GC fait la déduplication côté
   serveur, donc pas de casse, juste de la latence (200 × 3s ≈ 10 min).
   Accepté comme fallback.

**Alternatives écartées** :
- (a) Upload de tout, GC déduplique : simple mais 200 requêtes inutiles + 10 min
  de latence aveugle. Rejeté pour l'UX.
- (b) Sélection manuelle pure, sans pré-sélection : oblige l'utilisateur à
  tout cocher à la main. Rejeté pour l'UX.

**Conséquences** :
- Le controller doit exposer `select_new_only()` (pré-sélection) et
  `select_all()` (force).
- La vue affiche le statut `already_transferred` par ligne.
- Le bouton « Synchroniser (N) » compte uniquement les sélectionnés (qu'ils
  soient déjà transférés ou non — le skip est géré par le backend).

## Périmètre de ce brief — Frontend uniquement

Tu livres la **couche UI**. Tu ne modifies pas le backend (Core + Services
sont figés).

- Extension `ui/watch_view.py` : la zone Montre passe de placeholder à
  fonctionnelle (liste des fichiers, sélection, bouton « Synchroniser vers GC »,
  barre de progression, résumé).
- Création `ui/activities_controller.py` : logique de présentation testable
  sans GTK (pattern `WorkoutsController`).
- Tests unitaires pour le controller.

La zone GC workouts (gauche) n'est pas modifiée — elle est fonctionnelle
depuis l'Epic 2.

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- L'UI appelle uniquement les Services (`sync/`) et l'Authenticator. Jamais
  `garmin/`, `watch/`, `store/` directement (sauf `WatchDetector` qui est Core
  mais exposé comme service de détection — validé par le DP, cf. Epic 2).
- L'UI ne réimplémente aucune logique métier : pas de filtrage, pas de tri, pas
  de dédup. Tout vient du backend.
- L'UI n'importe jamais `garminconnect` directement.

### Threading (figé, option A)

Identique à l'Epic 2 frontend. GTK4 a une boucle d'événements principale sur
un seul thread. Tout appel réseau/USB (`list_uploadable_files`,
`push_activities`) **doit** s'exécuter hors du thread GTK.

Schéma imposé (déjà utilisé par `WorkoutsController` et `AuthView`) :

1. Lancement du travail dans un `threading.Thread(daemon=True)`.
2. Les callbacks vers l'UI (progression, résultat, erreur) passent par
   `GLib.idle_add()` qui les exécute sur le thread GTK.
3. **Jamais** de manipulation de widgets hors du thread GTK.

Référence d'implémentation : `ui/workouts_controller.py`
(`_fetch_worker` + `_on_fetch_success`, `_push_worker` +
`_on_push_success`), `ui/auth_view.py` (`_login_worker`).

### Tests UI (figé)

GTK4 est testable mais lourd. La logique de présentation (état de la liste,
sélection, activation du bouton, calcul du compte, gestion des états de
transfert, pré-sélection des fichiers nouveaux) est extraite dans
`ui/activities_controller.py`, une classe **sans dépendance GTK** (pas d'import
de `gi.repository`). Les widgets GTK restent minces dans `watch_view.py` et
délèguent au controller.

Les tests unitaires portent sur le controller. Pas de tests d'intégration GTK
dans cet epic (couverture UI cible > 60 %, ADR-008).

## Contrats backend figés (rappel)

Ces signatures sont le contrat sur lequel tu t'appuies. Elles ne bougeront
pas. Source : `docs/dev/Epic-3-brief.md` + `src/openrunner55/sync/activities.py`.

### `sync/activities.py`

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class UploadableFile:
    """Un fichier .FIT sur la montre, candidat à l'upload vers GC."""
    path: Path                 # chemin relatif à GARMIN/ (ex. "Activity/2026-08-07-08-29-33.fit")
    category: str             # "activity" | "monitor" | "sleep" | "metrics"
    size: int                 # taille en octets
    already_transferred: bool # True si déjà uploadé (dédup locale)

@dataclass
class SyncResult:
    """Bilan d'une opération `push_activities`."""
    total: int
    success: int
    failed: int
    errors: list[str]   # un message par fichier échoué ("file {path}: {ExcType}: {msg}")
    skipped: int       # fichiers ignorés (déjà transférés)

UPLOADABLE_CATEGORIES = ("Activity", "Monitor", "Sleep", "Metrics")
EXCLUDED_CATEGORIES = ("SUMMARY",)

def list_uploadable_files(
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
) -> list[UploadableFile]:
    """Liste les fichiers .FIT uploadables sur la montre, avec statut de dédup.

    Tri : par catégorie (ordre de UPLOADABLE_CATEGORIES) puis par nom de
    fichier (chronologique pour Activity/).
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

    Les fichiers already_transferred=True sont skippés (pas d'appel API).
    En cas d'échec d'un fichier, on continue au suivant (erreur collectée).
    """
```

**Points d'attention contrat** :

- `list_uploadable_files` retourne des `UploadableFile` avec le chemin
  **relatif à GARMIN/**. Le frontend dispose déjà de la liste — il transmet
  les `UploadableFile` sélectionnés à `push_activities`.
- `push_activities` reçoit `items: list[UploadableFile]` (pas juste des
  chemins). Pas de re-listing.
- `push_activities` skippe les `already_transferred=True` (dédup). Le compte
  `skipped` est dans le `SyncResult`.
- `SyncResult.errors` : chaînes préformatées `"file {path}: {ExcType}: {msg}"`,
  à afficher telles quelles dans le résumé d'échec (comme l'Epic 2).
- `SyncResult.skipped` : nombre de fichiers skippés (déjà transférés). À
  afficher dans le résumé (« N skippés ») pour que l'utilisateur comprenne
  pourquoi le compte success < total.

### `watch/detector.py` — `WatchDetector` (existant, non modifié)

```python
class WatchDetector:
    def is_connected() -> bool
    def get_mount_path() -> Path | None
    def on_status_changed(callback: Callable[[bool], None])  # signal thread-safe
    def start() -> None
    def stop() -> None    # idempotent, join(timeout=2s)
```

Déjà branché dans `ui/app.py` depuis l'Epic 2. Le `ActivitiesController`
s'abonne au même signal `on_status_changed` (via le `WatchDetector` partagé
ou un callback relayé par l'app — au choix du dev, cohérent avec l'Epic 2).

### `garmin/client.py` — `GarminClient` (existant, non modifié)

Le client authentifié est obtenu via `Authenticator.get_client()` (Epic 1).
L'UI ne construit pas de `GarminClient` elle-même.

## Fichiers à créer ou étendre

### `ui/watch_view.py` (existant — à étendre)

La zone Montre (droite, `_build_watch_section`) passe de placeholder à
fonctionnelle. Layout conforme `docs/conception/ux-design.md` §4.1 :

- **Zone droite — Montre — FR55** (fonctionnelle) :
  - Titre « Montre — FR55 » + sous-titre « Fichiers (N) » mis à jour en temps
    réel (N = nombre de fichiers uploadables listés).
  - Liste (`Gtk.ListBox`) avec une `Gtk.CheckButton` + nom du fichier + statut
    (déjà transféré / nouveau) par ligne. Le nom affiché est `path.name` (ex.
    `2026-08-07-08-29-33.fit`). La catégorie peut être indiquée en libellé
    secondaire grisé (ex. « Activity ») ou via un regroupement — au choix du
    dev, rester sobre.
  - Indication visuelle du statut `already_transferred` : ligne grisée ou
    icône ✓ pour les déjà transférés, ligne normale pour les nouveaux.
  - Bouton « Tout sélectionner » / « Tout désélectionner » (toggle) en haut
    de la liste.
  - Bouton « ↻ Synchroniser (N) » en bas de la zone :
    - Inactif si N=0 (sélection vide) ou montre déconnectée ou sync en cours.
    - `suggested-action` si N≥1 et montre connectée et inactif.
    - Compte N mis à jour en temps réel (sélection, pas total liste).
  - Spinner centré pendant le chargement de la liste
    (`list_uploadable_files`).
  - Si la montre n'est pas connectée : label « Branchez votre montre FR55 en
    USB » (cohérent avec l'Epic 2, même si la zone est maintenant
    fonctionnelle — la liste ne se charge qu'à la connexion).
- **Barre de progression** (pendant un envoi) :
  - `Gtk.Revealer` ou overlay en bas de la zone Montre.
  - `Gtk.ProgressBar` + texte « Fichier X/N — {nom} » + pourcentage.
  - Pas de bouton d'annulation (cohérent avec l'Epic 2).
- **Résumé d'envoi** (après `push_activities`) :
  - Succès total : « N fichiers envoyés » (+ « M skippés » si skipped > 0).
  - Échec partiel : « X/N envoyés. Y échecs. » (+ « M skippés ») + détail par
    fichier (`SyncResult.errors`).
  - Échec total : « Échec de l'envoi. » + détails.
  - Les fichiers échoués restent cochés pour réessayer (UX parcours C,
    cohérent avec l'Epic 2). Les fichiers skippés (déjà transférés) sont
    décochés s'ils étaient sélectionnés.

La vue délègue toute la logique de présentation à `ActivitiesController`.

**Note d'intégration** : la zone Montre ne se charge que lorsque la montre est
connectée. Au branchement (`on_watch_status_changed(True)`), le controller
lance `list_uploadable_files_async`. Au débranchement, la liste est vidée et
le placeholder « Branchez votre montre » réapparaît.

### `ui/activities_controller.py` (nouveau)

Logique de présentation testable sans GTK. Pas d'import de `gi.repository`.
Pattern miroir de `WorkoutsController`.

```python
class ActivitiesController:
    """Logique de présentation de la zone Montre (testable sans GTK).

    Pas de dépendance GTK — testable unitairement avec des mocks.
    La vue connecte les signaux GTK aux méthodes du controller, et le
    controller notifie la vue via des callbacks.
    """

    def __init__(
        self,
        client: GarminClient,
        watch_factory: Callable[[Path], WatchFilesystem],
        transfers: TransferredFilesStore,
        history: SyncHistoryStore,
        logger: OperationLogger,
        detector: WatchDetector,
        scheduler: Callable[..., None] | None = None,
    ) -> None: ...

    # -- état de la liste --
    @property
    def files(self) -> list[UploadableFile]: ...
    @property
    def is_loading(self) -> bool: ...

    # -- sélection --
    @property
    def selected(self) -> set[Path]: ...   # ensemble de chemins relatifs
    def toggle_selection(self, path: Path) -> None: ...
    def select_all(self) -> None: ...          # sélectionne tout (y compris déjà transférés)
    def select_new_only(self) -> None: ...    # sélectionne uniquement already_transferred=False
    def select_none(self) -> None: ...
    @property
    def selected_count(self) -> int: ...

    # -- activation du bouton synchroniser --
    @property
    def can_sync(self) -> bool: ...
    # True si : sélection non vide ET montre connectée ET pas en cours
    # de sync ET pas en cours de chargement de la liste.

    # -- état du transfert --
    @property
    def is_sending(self) -> bool: ...
    @property
    def progress(self) -> tuple[int, int, str] | None: ...
    # (current, total, current_file_name) ou None si pas en cours.
    @property
    def last_result(self) -> SyncResult | None: ...

    # -- actions (lancées dans un thread par la vue) --
    def list_uploadable_files_async(self, on_done, on_error) -> None: ...
    def push_activities_async(
        self, on_progress, on_done, on_error
    ) -> None: ...
    # on_progress(current, total, name) — appelé avant chaque fichier.
    # on_done(SyncResult) — appelé à la fin.
    # on_error(Exception) — appelé si une erreur non gérée par push_activities
    #   survient (push_activities gère déjà les échecs par fichier via
    #   SyncResult.errors ; on_error est pour les erreurs fatales comme
    #   une montre déconnectée avant le premier upload).

    # -- callbacks de la vue (à connecter par la vue) --
    def on_files_changed(self, callback: Callable[[], None]) -> None: ...
    def on_selection_changed(self, callback: Callable[[], None]) -> None: ...
    def on_sending_state_changed(self, callback: Callable[[], None]) -> None: ...
    def on_watch_status_changed(self, connected: bool) -> None: ...
```

**Notes** :

- Le controller ne touche pas aux widgets. Il expose un état et des
  callbacks. La vue s'abonne et rafraîchit les widgets quand un callback est
  déclenché.
- `list_uploadable_files_async` et `push_activities_async` lancent le thread et
  utilisent le scheduler injecté (`GLib.idle_add` en production, synchrone en
  test) pour les callbacks — pattern identique à `WorkoutsController`.
- `on_watch_status_changed` est branché au signal `WatchDetector.on_status_changed`.
  Au branchement (`True`), le controller lance
  `list_uploadable_files_async`. Au débranchement (`False`), il vide la liste
  et la sélection.
- `select_new_only()` est appelé automatiquement après un `list_uploadable_files`
  réussi (pré-sélection des fichiers nouveaux, cf. décision de cadrage).
- `push_activities_async` transmet les `UploadableFile` sélectionnés (pas juste
  les chemins) à `push_activities` — le backend a déjà les objets.

### `ui/__init__.py` (existant)

Déjà vide. Rien à faire.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

### Fichier de test à créer

- `tests/unit/test_activities_controller.py` — `ActivitiesController` : logique
  de présentation avec `GarminClient`, `WatchFilesystem`,
  `TransferredFilesStore`, `SyncHistoryStore`, `OperationLogger`,
  `WatchDetector` mockés.

### À tester

- **État de la liste** : `list_uploadable_files_async` met à jour `files` et
  `is_loading` ; callback `on_files_changed` déclenché.
- **Pré-sélection automatique** : après un `list_uploadable_files_async`
  réussi, `selected` contient uniquement les fichiers
  `already_transferred=False` ; callback `on_selection_changed` déclenché.
- **Sélection** : `toggle_selection` ajoute/retire un chemin ; `selected_count`
  mis à jour ; `select_all` / `select_new_only` / `select_none` ; callback
  `on_selection_changed`.
- **Activation du bouton** : `can_sync` est False si sélection vide, False si
  montre déconnectée, False si `is_loading` ou `is_sending`, True sinon.
- **Envoi** : `push_activities_async` déclenche `on_progress` avant chaque
  fichier, `on_done(SyncResult)` à la fin, `is_sending` passe à True puis
  False. Les `items` transmis à `push_activities` sont bien les
  `UploadableFile` sélectionnés.
- **Skipped** : `SyncResult.skipped` est exposé via `last_result` et
  utilisable par la vue (le test vérifie que le controller ne l'écrase pas).
- **Statut montre** : `on_watch_status_changed(False)` désactive `can_sync`,
  vide `files` et `selected`. `on_watch_status_changed(True)` déclenche
  `list_uploadable_files_async` (vérifier que le lancement n'a lieu qu'une
  fois, pas de re-entrant).
- **Scheduler injecté** : utiliser un scheduler synchrone dans les tests
  (les callbacks s'exécutent immédiatement) pour observer l'état sans boucle
  GTK.

### Commande

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (205 existants + nouveaux controller). Les tests
d'intégration (montre réelle) et réseau (upload réel GC) sont pour le
jalon E4, pas pour cette session.

## Références dans le repo

- `docs/decisions/adr-002.md` — architecture 3 couches, interfaces publiques
- `docs/decisions/adr-003.md` — GTK 4 + libadwaita
- `docs/decisions/adr-005.md` — SQLite + `check_same_thread=False` (révisé E3)
- `docs/decisions/adr-006.md` — détection USB pyudev + polling
- `docs/decisions/adr-007.md` — retry/backoff 429, délai inter-requêtes
- `docs/decisions/adr-008.md` — stratégie de tests
- `docs/conception/ux-design.md` — wireframes, parcours C, design system
- `docs/dev/Epic-2-brief-frontend.md` — brief frontend de référence (pattern)
- `docs/dev/Epic-2-notes-frontend.md` — notes de dev frontend (choix, écarts)
- `docs/dev/Epic-3-brief.md` — brief backend (contrats figés)
- `docs/dev/Epic-3-notes-backend.md` — notes de dev backend (décisions, écarts)
- `src/openrunner55/ui/app.py` — shell existant (navigation, HeaderBar)
- `src/openrunner55/ui/watch_view.py` — vue à étendre (zone Montre placeholder)
- `src/openrunner55/ui/workouts_controller.py` — controller de référence (pattern)
- `src/openrunner55/ui/auth_view.py` — référence de threading + style de code
- `src/openrunner55/sync/activities.py` — service `list_uploadable_files`/`push_activities`
- `src/openrunner55/watch/detector.py` — `WatchDetector`
- `docs/branching-rules.md` — règles de branches

## Critères de done (frontend)

- `ui/watch_view.py` étendu : zone Montre fonctionnelle (liste des fichiers,
  sélection, bouton « Synchroniser vers GC », barre de progression, résumé,
  pré-sélection des fichiers nouveaux, indication visuelle du statut
  `already_transferred`).
- `ui/activities_controller.py` créé : logique de présentation sans dépendance
  GTK.
- `tests/unit/test_activities_controller.py` créé : tests du controller.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.ui.watch_view` ne lève pas d'erreur.
- Aucun appel réseau sur le thread GTK (threading + `GLib.idle_add`).
- Aucun mot de passe ou token dans les logs ou l'UI.
- L'UI n'importe jamais `garminconnect` directement.
- L'UI n'appelle jamais `garmin/`, `watch/`, `store/` directement (sauf
  `WatchDetector` — validé par le DP, cohérent avec l'Epic 2).
- Pas de TODO non résolu dans le code livré.

## Ordre de construction — étapes avec validation

Chaque étape = un checkpoint. Tests verts + commit + validation du Directeur
de Projet avant de passer à la suivante.

| Étape | Fichiers | Dépendances |
|-------|----------|-------------|
| **1** | `ui/activities_controller.py` + `tests/unit/test_activities_controller.py` (état liste, sélection, pré-sélection, `can_sync`) | `sync/activities.py`, `watch/detector.py` (contrats figés) |
| **2** | `ui/watch_view.py` (zone Montre : liste, statut `already_transferred`, bouton « Tout sélectionner », bouton « Synchroniser ») branché au controller | étape 1 |
| **3** | `ui/watch_view.py` (threading `list_uploadable_files_async` : chargement liste + spinner, déclenchement au branchement montre) | étapes 1-2 |
| **4** | `ui/watch_view.py` (threading `push_activities_async` : envoi, barre de progression, résumé avec `skipped`) | étapes 1-3 |

À la fin de l'étape 4, la batterie complète `pytest tests/ -m unit -v` doit
passer (Epic 1 + Epic 2 + Epic 3 backend + frontend). Le Directeur de Projet
valide then merge.

## Branche

`feat/epic-3-frontend`. Commits fréquents avec messages conventionnels
(`feat:`, `test:`, `chore:`). Un commit par étape minimum.
