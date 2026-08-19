# Brief de mission — Epic 2 : Workouts Cloud → Montre (Frontend)

Tu es le Developer Frontend du projet OpenRunner55. Voici ta mission pour
l'Epic 2 frontend.

## Contexte rapide

OpenRunner55 est une app desktop Linux (Python 3.12+, GTK4/libadwaita) qui
remplace Garmin Express pour une montre Garmin FR55. Le projet est en phase
Développement.

**Epic 1 (Auth) livré.** `ui/app.py` (shell `OpenRunnerApp`) et
`ui/auth_view.py` (écran de login) existent. Le shell affiche actuellement un
placeholder « Connecté — vues métier à venir » après authentification.

**Epic 2 backend livré et mergé.** Les contrats backend sont figés (cf.
section « Contrats backend figés » ci-dessous). Le frontend s'y appuie.

L'Epic 2 frontend ajoute l'UI du sens **Cloud → Montre** : shell principal
post-auth avec navigation, section Activité (zone GC workouts fonctionnelle +
zone Montre en placeholder), envoi des workouts sélectionnés vers la FR55.

## Périmètre (MVP)

Stories concernées :

- **US-2.1** — Lister les workouts GC triés du plus récent au plus ancien
  (nom, pas d'ID visible, pas de date — le tri suffit)
- **US-2.3** — Sélection multiple de workouts via checkboxes + envoi vers la
  montre FR55 branchée en USB (téléchargement .FIT → copie → confirmation)

**Hors périmètre MVP** (noté pour plus tard, ne pas implémenter) :

- Détection des doublons (workouts déjà présents sur la montre) → US-2.2
  (Should)
- Zone Montre (liste des activités) → Epic 3
- Bouton « ↻ Synchroniser » (remontée Montre → GC) → Epic 3
- Section Logs & Historique (contenu) → Epic 4
- Section Compte & Paramètres (contenu) → Epic 4
- Pagination de la liste GC (limite 20 workouts héritée de `get_workouts`) —
  noté pour plus tard, on affiche les 20 premiers dans l'Epic 2

## Périmètre de ce brief — Frontend uniquement

Tu livres la **couche UI**. Tu ne modifies pas le backend (Core + Services
sont figés).

- Extension `ui/app.py` (shell post-auth avec navigation)
- `ui/watch_view.py` (section Activité : zone GC workouts + zone Montre
  placeholder)
- `ui/workouts_controller.py` (logique de présentation testable sans GTK)
- Tests unitaires pour le controller

Les sections Logs & Historique et Compte & Paramètres sont des placeholders
vides (titre de section seulement). Leur contenu viendra aux Epics 3-4.

## Règles d'architecture (non négociables)

Rappel ADR-002 — architecture 3 couches : **UI → Services → Core**.

- L'UI appelle uniquement les Services (`sync/`) et l'Authenticator. Jamais
  `garmin/`, `watch/`, `store/` directement (sauf `sync/history.py` en lecture
  seule, pont UI → store — non utilisé dans cet epic).
- L'UI ne réimplémente aucune logique métier : pas de slugify, pas de tri, pas
  de dédup. Tout vient du backend.
- L'UI n'importe jamais `garminconnect` directement.

### Threading (figé, option A)

GTK4 a une boucle d'événements principale sur un seul thread. Tout appel
réseau (`fetch_workouts`, `push_workouts`) **doit** s'exécuter hors du thread
GTK, sous peine de figer l'UI.

Schéma imposé (déjà utilisé par `WatchDetector` et `AuthView`) :

1. Lancement du travail dans un `threading.Thread(daemon=True)`.
2. Les callbacks vers l'UI (progression, résultat, erreur) passent par
   `GLib.idle_add()` qui les exécute sur le thread GTK.
3. **Jamais** de manipulation de widgets hors du thread GTK.

Référence d'implémentation : `ui/auth_view.py` (`_login_worker` +
`_on_login_success`/`_on_login_failure`), `ui/app.py`
(`_restore_session_worker` + `_on_session_restored`).

### Tests UI (figé)

GTK4 est testable mais lourd. La logique de présentation (état de la
sélection, activation du bouton, calcul du compte, gestion des états de
transfert) est extraite dans `ui/workouts_controller.py`, une classe **sans
dépendance GTK** (pas d'import de `gi.repository`). Les widgets GTK restent
minces dans `watch_view.py` et délèguent au controller.

Les tests unitaires portent sur le controller. Pas de tests d'intégration GTK
dans cet epic (couverture UI cible > 60 %, ADR-008).

## Contrats backend figés (rappel)

Ces signatures sont le contrat sur lequel tu t'appuies. Elles ne bougeront
pas.

### `sync/workouts.py`

```python
@dataclass
class WorkoutSummary:
    workout_id: int
    name: str
    date: datetime | None   # None si absente — gérer dans l'affichage
    type: str               # sport / catégorie

@dataclass
class SyncResult:
    total: int
    success: int
    failed: int
    errors: list[str]       # chaînes préformatées "workout {id}: {ExcType}: {msg}"

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

**Points d'attention contrat** :

- `push_workouts` reçoit `items: list[WorkoutSummary]` (pas `ids`). Le
  frontend dispose déjà de la liste via `fetch_workouts` — il transmet les
  `WorkoutSummary` sélectionnés.
- `push_workouts` ne skippe pas les déjà-transférés. Un re-sync crée
  `foo_2.FIT` sur la montre. L'UI ne bloque pas un re-envoi sur la base de
  `is_transferred` (US-2.2 est Should, hors MVP).
- `SyncResult.errors` : chaînes préformatées, à afficher telles quelles dans
  le résumé d'échec.
- Limite 20 workouts dans `fetch_workouts` (héritée de `get_workouts`). Pas
  de pagination dans cet epic — on affiche les 20 premiers.

### `watch/detector.py` — `WatchDetector`

```python
class WatchDetector:
    def is_connected() -> bool
    def get_mount_path() -> Path | None
    def on_status_changed(callback: Callable[[bool], None])  # signal thread-safe
    def start() -> None   # ajouté au-delà du contrat ADR-002 — cycle de vie
    def stop() -> None    # idempotent, join(timeout=2s)
```

- `start()` à appeler post-auth (quand le shell principal s'affiche).
- `stop()` à appeler à la fermeture de l'app.
- `on_status_changed` émet via `GLib.idle_add` (thread-safe) — le callback
  peut manipuler des widgets directement.
- Pas de mécanisme de désinscription (dette suivie). Un seul callback global
  pour l'app.

### `garmin/client.py` — `GarminClient`

Le client authentifié est obtenu via `Authenticator.get_client()` (Epic 1).
L'UI ne construit pas de `GarminClient` elle-même.

## Fichiers à créer ou étendre

### `ui/app.py` (existant — à étendre)

Remplacer le placeholder « Connecté — vues métier à venir » par le shell
principal post-auth :

- `Adw.NavigationSplitView` avec navigation latérale (3 entrées : Activité,
  Logs & Historique, Compte & Paramètres).
- Section active par défaut : Activité.
- Les sections non couvertes affichent un placeholder simple (titre de
  section + label « À venir »).
- `Adw.HeaderBar` avec indicateur de connexion montre (puce verte/grise)
  mis à jour via `WatchDetector.on_status_changed`.
- **Pas de bouton « ↻ Synchroniser »** dans la HeaderBar (réservé Epic 3).
- `WatchDetector.start()` appelé post-auth (quand le shell s'affiche).
- `WatchDetector.stop()` appelé à la fermeture de la fenêtre (sur
  `close-request` ou `shutdown`).

L'instance de `WatchDetector` est détenue par l'app (ou par le shell). Le
callback `on_status_changed` met à jour la puce de la HeaderBar.

### `ui/watch_view.py` (nouveau)

Section Activité. Layout conforme `docs/conception/ux-design.md` §4.1 :

- Split horizontal 40/60 entre zone GC (gauche) et zone Montre (droite).
- **Zone gauche — Garmin Connect** (fonctionnelle) :
  - Titre « Garmin Connect » + sous-titre « Workouts (N) » mis à jour en
    temps réel.
  - Liste (`Gtk.ListBox` ou `Gtk.ColumnView`) avec une `Gtk.CheckButton` +
    nom du workout par ligne. Pas d'ID visible, pas de date.
  - Bouton « ▶ Envoyer (N) » en bas de la carte :
    - Inactif si N=0 ou montre déconnectée ou transfert en cours.
    - `suggested-action` si N≥1 et montre connectée et inactif.
    - Compte N mis à jour en temps réel.
  - Spinner centré pendant le chargement de la liste.
- **Zone droite — Montre** (placeholder) :
  - Titre « Montre — FR55 ».
  - Contenu : label centré grisé « Réservé à l'Epic 3 » (ou similaire).
  - Si la montre n'est pas connectée : label « Branchez votre montre FR55
    en USB » (cohérent avec l'UX, même si la zone est un placeholder).
- **Barre de progression** (pendant un envoi) :
  - `Gtk.Revealer` ou overlay en bas de la zone GC.
  - `Gtk.ProgressBar` + texte « Workout X/N — {nom} » + pourcentage.
  - Pas de bouton d'annulation.
- **Résumé d'envoi** (après `push_workouts`) :
  - Succès total : « N workouts envoyés ».
  - Échec partiel : « X/N envoyés. Y échecs. » + détail par fichier
    (`SyncResult.errors`).
  - Échec total : « Échec de l'envoi. » + détails.
  - Les workouts échoués restent cochés pour réessayer (UX parcours C).

La vue délègue toute la logique de présentation à `WorkoutsController`.

### `ui/workouts_controller.py` (nouveau)

Logique de présentation testable sans GTK. Pas d'import de `gi.repository`.

```python
class WorkoutsController:
    """Logique de présentation de la zone GC workouts.

    Pas de dépendance GTK — testable unitairement avec des mocks.
    La vue connecte les signaux GTK aux méthodes du controller, et le
    controller notifie la vue via des callbacks.
    """

    def __init__(
        self,
        client: GarminClient,
        watch: WatchFilesystem,
        transfers: TransferredFilesStore,
        history: SyncHistoryStore,
        logger: OperationLogger,
        detector: WatchDetector,
    ) -> None: ...

    # -- état de la liste --
    @property
    def workouts(self) -> list[WorkoutSummary]: ...
    @property
    def is_loading(self) -> bool: ...

    # -- sélection --
    @property
    def selected(self) -> set[int]: ...   # ensemble de workout_id
    def toggle_selection(self, workout_id: int) -> None: ...
    def select_all(self) -> None: ...
    def select_none(self) -> None: ...
    @property
    def selected_count(self) -> int: ...

    # -- activation du bouton envoyer --
    @property
    def can_send(self) -> bool: ...
    # True si : sélection non vide ET montre connectée ET pas en cours
    # de transfert ET pas en cours de chargement de la liste.

    # -- état du transfert --
    @property
    def is_sending(self) -> bool: ...
    @property
    def progress(self) -> tuple[int, int, str] | None: ...
    # (current, total, current_workout_name) ou None si pas en cours.
    @property
    def last_result(self) -> SyncResult | None: ...

    # -- actions (lancées dans un thread par la vue) --
    def fetch_workouts_async(self, on_done, on_error) -> None: ...
    def push_workouts_async(
        self, on_progress, on_done, on_error
    ) -> None: ...
    # on_progress(current, total, name) — appelé avant chaque workout.
    # on_done(SyncResult) — appelé à la fin.
    # on_error(Exception) — appelé si une erreur non gérée par push_workouts
    #   survient (push_workouts gère déjà les échecs par workout via
    #   SyncResult.errors ; on_error est pour les erreurs fatales comme
    #   une montre déconnectée avant le premier download).

    # -- callbacks de la vue (à connecter par la vue) --
    def on_workouts_changed(self, callback: Callable[[], None]) -> None: ...
    def on_selection_changed(self, callback: Callable[[], None]) -> None: ...
    def on_sending_state_changed(self, callback: Callable[[], None]) -> None: ...
    def on_watch_status_changed(self, connected: bool) -> None: ...
```

**Notes** :

- Le controller ne touche pas aux widgets. Il expose un état et des
  callbacks. La vue s'abonne et rafraîchit les widgets quand un callback est
  déclenché.
- `fetch_workouts_async` et `push_workouts_async` lancent le thread et
  utilisent `GLib.idle_add` pour les callbacks — mais comme le controller ne
  dépend pas de GTK, il faut injecter le scheduler (`GLib.idle_add` ou un
  callable par défaut synchrone pour les tests). Voir « Tests » ci-dessous.
- `on_watch_status_changed` est branché au signal `WatchDetector.on_status_changed`.

### `ui/__init__.py` (existant)

Déjà vide. Rien à faire.

## Tests

ADR-008. Marqueur `@pytest.mark.unit`. Mocks uniquement.

### Fichier de test à créer

- `tests/unit/test_workouts_controller.py` — `WorkoutsController` : logique
  de présentation avec `GarminClient`, `WatchFilesystem`, `TransferredFilesStore`,
  `SyncHistoryStore`, `OperationLogger`, `WatchDetector` mockés.

### À tester

- **État de la liste** : `fetch_workouts_async` met à jour `workouts` et
  `is_loading` ; callback `on_workouts_changed` déclenché.
- **Sélection** : `toggle_selection` ajoute/retire un id ; `selected_count`
  mis à jour ; `select_all`/`select_none` ; callback `on_selection_changed`.
- **Activation du bouton** : `can_send` est False si sélection vide, False si
  montre déconnectée, False si `is_loading` ou `is_sending`, True sinon.
- **Envoi** : `push_workouts_async` déclenche `on_progress` avant chaque
  workout, `on_done(SyncResult)` à la fin, `is_sending` passe à True puis
  False. Les `items` transmis à `push_workouts` sont bien les
  `WorkoutSummary` sélectionnés.
- **Statut montre** : `on_watch_status_changed(False)` désactive `can_send`.
- **Scheduler injecté** : utiliser un scheduler synchrone dans les tests
  (les callbacks s'exécutent immédiatement) pour observer l'état sans boucle
  GTK.

### Commande

```bash
python -m pytest tests/ -m unit -v
```

Doit passer à 100 % (tests existants + nouveaux controller). Les tests
d'intégration (montre réelle) et réseau (download réel GC) sont pour le
jalon E2, pas pour cette session.

## Références dans le repo

- `docs/decisions/adr-002.md` — architecture 3 couches, interfaces publiques
- `docs/decisions/adr-003.md` — GTK 4 + libadwaita
- `docs/decisions/adr-006.md` — détection USB pyudev + polling
- `docs/decisions/adr-008.md` — stratégie de tests
- `docs/conception/ux-design.md` — wireframes, parcours C, design system
- `docs/dev/Epic-2-brief.md` — brief backend (contrats figés)
- `docs/dev/Epic-2-notes-backend.md` — notes de dev backend (choix, écarts)
- `src/openrunner55/ui/app.py` — shell existant à étendre
- `src/openrunner55/ui/auth_view.py` — référence de threading + style de code
- `src/openrunner55/sync/workouts.py` — service `fetch_workouts`/`push_workouts`
- `src/openrunner55/watch/detector.py` — `WatchDetector`
- `docs/branching-rules.md` — règles de branches

## Critères de done (frontend)

- `ui/app.py` étendu : shell post-auth avec navigation 3 sections (Activité
  fonctionnelle, 2 placeholders), HeaderBar avec indicateur montre,
  `WatchDetector.start()`/`stop()` branchés.
- `ui/watch_view.py` créé : zone GC workouts fonctionnelle (liste, sélection,
  bouton envoyer, barre de progression, résumé) + zone Montre placeholder.
- `ui/workouts_controller.py` créé : logique de présentation sans dépendance
  GTK.
- `tests/unit/test_workouts_controller.py` créé : tests du controller.
- `python -m pytest tests/ -m unit -v` passe à 100 %.
- `import openrunner55.ui.watch_view` ne lève pas d'erreur.
- Aucun appel réseau sur le thread GTK (threading + `GLib.idle_add`).
- Aucun mot de passe ou token dans les logs ou l'UI.
- L'UI n'importe jamais `garminconnect` directement.
- L'UI n'appelle jamais `garmin/`, `watch/`, `store/` directement (sauf
  `WatchDetector` qui est Core mais exposé comme service de détection —
  validé par le DP).
- Pas de TODO non résolu dans le code livré.

## Ordre de construction — étapes avec validation

Chaque étape = un checkpoint. Tests verts + commit + validation du Directeur
de Projet avant de passer à la suivante.

| Étape | Fichiers | Dépendances |
|-------|----------|-------------|
| **1** | `ui/app.py` (extension shell : navigation 3 sections + placeholders, HeaderBar indicateur montre, `WatchDetector.start/stop`) | `WatchDetector` (existant), `ui/auth_view.py` (existant) |
| **2** | `ui/workouts_controller.py` + `tests/unit/test_workouts_controller.py` | `sync/workouts.py`, `watch/detector.py` (contrats figés) |
| **3** | `ui/watch_view.py` (zone GC : liste, sélection, bouton envoyer) branché au controller | étape 2 |
| **4** | `ui/watch_view.py` (threading `fetch_workouts_async` : chargement liste + spinner) | étapes 2-3 |
| **5** | `ui/watch_view.py` (threading `push_workouts_async` : envoi, barre de progression, résumé) | étapes 2-4 |

À la fin de l'étape 5, la batterie complète `pytest tests/ -m unit -v` doit
passer (Epic 1 + Epic 2 backend + frontend). Le Directeur de Projet valide
then merge.

## Branche

`feat/epic-2-frontend`. Commits fréquents avec messages conventionnels
(`feat:`, `test:`, `chore:`). Un commit par étape minimum.
