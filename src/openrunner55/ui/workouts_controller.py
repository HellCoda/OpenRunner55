"""Logique de présentation de la zone GC workouts (couche UI, sans GTK).

`WorkoutsController` extrait de la vue GTK toute la logique testable
unitairement : état de la liste, sélection, activation du bouton « Envoyer »,
état du transfert. Il ne touche jamais aux widgets — il expose un état et des
callbacks ; la vue s'abonne et rafraîchit l'interface quand un callback est
déclenché (pattern observateur).

Contraintes d'architecture (ADR-002) :

- **Pas d'import de `gi.repository`** : le controller est testable avec des
  mocks, sans boucle GTK.
- **Pas d'import des modules Core** (`garmin/`, `watch/`, `store/`) à
  l'exécution : les dépendances Core lui sont injectées (duck-typing) et leurs
  types ne sont référencés que sous `TYPE_CHECKING` (annotations seulement).
- **Toute la logique métier vient du Service** `sync/workouts.py`
  (`fetch_workouts`, `push_workouts`) : pas de slugify, pas de tri, pas de
  dédup réimplémentés ici.

Threading (brief Epic 2, option A) :

- `fetch_workouts_async` et `push_workouts_async` lancent un thread daemon ;
  le travail réseau/USB s'exécute hors du thread GTK.
- Les callbacks vers l'état (progression, résultat, erreur) sont marshallés
  vers le thread GTK via un *scheduler* injectable. En production la vue passe
  `GLib.idle_add` ; dans les tests on utilise le scheduler synchrone par défaut
  (invocation immédiate, observable sans boucle GTK).

Écart documenté par rapport à la signature du brief : le paramètre `watch` est
fourni sous forme de *factory* `Callable[[Path], WatchFilesystem]` plutôt que
d'une instance `WatchFilesystem` figée. Raison : le point de montage est
dynamique (il change à chaque branchement de la montre) et le controller ne
doit pas importer `watch/filesystem.py`. La factory résout le point de montage
courant au moment de l'envoi.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openrunner55.sync.workouts import (
    SyncResult,
    WorkoutSummary,
    fetch_workouts,
    push_workouts,
)

if TYPE_CHECKING:
    from openrunner55.garmin.client import GarminClient
    from openrunner55.store.history import SyncHistoryStore
    from openrunner55.store.logger import OperationLogger
    from openrunner55.store.transfers import TransferredFilesStore
    from openrunner55.watch.detector import WatchDetector
    from openrunner55.watch.filesystem import WatchFilesystem


class WatchNotConnectedError(RuntimeError):
    """La montre a été débranchée avant le début d'un envoi (erreur fatale)."""


def _direct_scheduler(callback: Callable[..., None], *args: Any) -> None:
    """Scheduler synchrone par défaut : invoque le callback immédiatement.

    Utilisé dans les tests pour observer l'état sans boucle GTK. En production,
    la vue injecte `GLib.idle_add` pour marshaller les callbacks vers le thread
    GTK principal.
    """
    callback(*args)


class WorkoutsController:
    """Logique de présentation de la zone GC workouts (testable sans GTK).

    :param client: client Garmin authentifié (injecté, duck-typed).
    :param watch_factory: construit un `WatchFilesystem` frais depuis un point
        de montage (`Callable[[Path], WatchFilesystem]`). Résout le point de
        montage au moment de l'envoi, sans import Core dans le controller.
    :param transfers: store des fichiers transférés (injecté).
    :param history: store de l'historique de sync (injecté).
    :param logger: logger d'opérations (injecté).
    :param detector: détecteur USB de la montre (Core exposé comme service).
    :param scheduler: marshalle les callbacks vers le thread GTK
        (`GLib.idle_add` en production, invocation synchrone en test).
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
    ) -> None:
        self._client = client
        self._watch_factory = watch_factory
        self._transfers = transfers
        self._history = history
        self._logger = logger
        self._detector = detector
        self._scheduler = scheduler or _direct_scheduler

        # -- état --
        self._workouts: list[WorkoutSummary] = []
        self._is_loading = False
        self._selected: set[int] = set()
        self._is_sending = False
        self._progress: tuple[int, int, str] | None = None
        self._last_result: SyncResult | None = None
        self._watch_connected: bool = detector.is_connected()

        # -- callbacks de la vue --
        self._on_workouts_changed_cb: Callable[[], None] | None = None
        self._on_selection_changed_cb: Callable[[], None] | None = None
        self._on_sending_state_changed_cb: Callable[[], None] | None = None

        # Branché au signal de détection : le changement d'état de la montre
        # réactive/désactive le bouton Envoyer (can_send en dépend).
        detector.on_status_changed(self.on_watch_status_changed)

    # -- état de la liste ----------------------------------------------------

    @property
    def workouts(self) -> list[WorkoutSummary]:
        """Liste des workouts GC affichés (tri récent → ancien, copie défensive)."""
        return list(self._workouts)

    @property
    def is_loading(self) -> bool:
        """True pendant la récupération de la liste (`fetch_workouts`)."""
        return self._is_loading

    # -- sélection -----------------------------------------------------------

    @property
    def selected(self) -> set[int]:
        """Ensemble des `workout_id` sélectionnés (copie défensive)."""
        return set(self._selected)

    def toggle_selection(self, workout_id: int) -> None:
        """Ajoute ou retire un workout de la sélection."""
        if workout_id in self._selected:
            self._selected.discard(workout_id)
        else:
            self._selected.add(workout_id)
        self._notify_selection_changed()

    def select_all(self) -> None:
        """Sélectionne tous les workouts affichés."""
        self._selected = {w.workout_id for w in self._workouts}
        self._notify_selection_changed()

    def select_none(self) -> None:
        """Désélectionne tout."""
        self._selected.clear()
        self._notify_selection_changed()

    @property
    def selected_count(self) -> int:
        """Nombre de workouts sélectionnés (pour le bouton « Envoyer (N) »)."""
        return len(self._selected)

    # -- état de la montre ---------------------------------------------------

    @property
    def watch_connected(self) -> bool:
        """True si la montre est détectée comme connectée (état suivi)."""
        return self._watch_connected

    # -- activation du bouton envoyer ---------------------------------------

    @property
    def can_send(self) -> bool:
        """True si : sélection non vide ET montre connectée ET pas de transfert
        en cours ET pas de chargement de liste en cours."""
        return (
            bool(self._selected)
            and self._watch_connected
            and not self._is_sending
            and not self._is_loading
        )

    # -- état du transfert ---------------------------------------------------

    @property
    def is_sending(self) -> bool:
        """True pendant un envoi vers la montre."""
        return self._is_sending

    @property
    def progress(self) -> tuple[int, int, str] | None:
        """`(current, total, current_workout_name)` ou None si pas en cours."""
        return self._progress

    @property
    def last_result(self) -> SyncResult | None:
        """Dernier `SyncResult` d'un envoi, ou None si aucun envoi terminé."""
        return self._last_result

    # -- callbacks de la vue (à connecter) ----------------------------------

    def on_workouts_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand la liste ou le chargement change."""
        self._on_workouts_changed_cb = callback

    def on_selection_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand la sélection change."""
        self._on_selection_changed_cb = callback

    def on_sending_state_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand l'état du transfert change."""
        self._on_sending_state_changed_cb = callback

    def on_watch_status_changed(self, connected: bool) -> None:
        """Branché au signal `WatchDetector.on_status_changed`.

        Met à jour l'état de connexion et notifie la vue (le bouton Envoyer
        dépend de la connexion).
        """
        self._watch_connected = connected
        self._notify_sending_state_changed()

    # -- actions asynchrones ------------------------------------------------

    def fetch_workouts_async(
        self,
        on_done: Callable[[list[WorkoutSummary]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Récupère les workouts GC dans un thread dédié (hors thread GTK).

        :param on_done: appelé (thread GTK) avec la liste triée des workouts.
        :param on_error: appelé (thread GTK) en cas d'échec de récupération.
        """
        if self._is_loading:
            return
        self._is_loading = True
        self._notify_workouts_changed()
        threading.Thread(
            target=self._fetch_worker, args=(on_done, on_error), daemon=True
        ).start()

    def refresh_workouts(
        self,
        on_done: Callable[[list[WorkoutSummary]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Relance le chargement de la liste des workouts (bouton « ↻ »).

        Alias sémantique de :meth:`fetch_workouts_async` : même comportement
        (garde anti-re-entrante via ``is_loading``), mais nomme l'intention
        utilisateur (rafraîchir) plutôt que l'opération technique (fetch). La
        vue connecte le bouton « ↻ » à cette méthode avec les mêmes callbacks
        que le chargement initial.

        :param on_done: appelé (thread GTK) avec la liste triée des workouts.
        :param on_error: appelé (thread GTK) en cas d'échec de récupération.
        """
        self.fetch_workouts_async(on_done, on_error)

    def push_workouts_async(
        self,
        on_progress: Callable[[int, int, str], None],
        on_done: Callable[[SyncResult], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Envoie les workouts sélectionnés vers la montre (thread dédié).

        :param on_progress: appelé (thread GTK) avant chaque workout avec
            `(current, total, name)`.
        :param on_done: appelé (thread GTK) avec le `SyncResult` agrégé.
        :param on_error: appelé (thread GTK) en cas d'erreur fatale (ex.
            montre débranchée avant le premier téléchargement). Les échecs par
            workout sont déjà gérés par `push_workouts` via `SyncResult.errors`.
        """
        if self._is_sending:
            return
        items = [w for w in self._workouts if w.workout_id in self._selected]
        if not items:
            return
        self._is_sending = True
        self._progress = (0, len(items), "")
        self._last_result = None
        self._notify_sending_state_changed()
        threading.Thread(
            target=self._push_worker,
            args=(items, on_progress, on_done, on_error),
            daemon=True,
        ).start()

    # -- workers ------------------------------------------------------------

    def _fetch_worker(self, on_done, on_error) -> None:
        try:
            workouts = fetch_workouts(self._client)
            self._scheduler(self._on_fetch_success, on_done, workouts)
        except Exception as exc:  # noqa: BLE001 - erreur fatale remontée à la vue
            self._scheduler(self._on_fetch_failure, on_error, exc)

    def _push_worker(self, items, on_progress, on_done, on_error) -> None:
        try:
            mount_path = self._detector.get_mount_path()
            if mount_path is None:
                raise WatchNotConnectedError(
                    "La montre a été débranchée avant le début de l'envoi."
                )
            watch = self._watch_factory(mount_path)

            total = len(items)
            success = 0
            failed = 0
            errors: list[str] = []
            succeeded_ids: list[int] = []
            for current, item in enumerate(items, start=1):
                # Progression « avant chaque workout », marshallée vers le GTK.
                self._scheduler(
                    self._apply_progress, on_progress, current, total, item.name
                )
                result = push_workouts(
                    self._client,
                    watch,
                    self._transfers,
                    self._history,
                    self._logger,
                    [item],
                )
                success += result.success
                failed += result.failed
                errors.extend(result.errors)
                if result.success:
                    succeeded_ids.append(item.workout_id)

            final = SyncResult(total=total, success=success, failed=failed, errors=errors)
            self._scheduler(self._on_push_success, on_done, final, succeeded_ids)
        except Exception as exc:  # noqa: BLE001 - erreur fatale remontée à la vue
            self._scheduler(self._on_push_failure, on_error, exc)

    # -- handlers (thread GTK) ----------------------------------------------

    def _on_fetch_success(self, on_done, workouts) -> None:
        self._is_loading = False
        self._workouts = workouts
        # Conserve uniquement les sélections dont le workout existe encore.
        new_selected = {w.workout_id for w in workouts} & self._selected
        if new_selected != self._selected:
            self._selected = new_selected
            self._notify_selection_changed()
        on_done(workouts)
        self._notify_workouts_changed()

    def _on_fetch_failure(self, on_error, exc) -> None:
        self._is_loading = False
        on_error(exc)
        self._notify_workouts_changed()

    def _apply_progress(self, on_progress, current, total, name) -> None:
        self._progress = (current, total, name)
        self._notify_sending_state_changed()
        on_progress(current, total, name)

    def _on_push_success(self, on_done, result, succeeded_ids) -> None:
        self._is_sending = False
        self._progress = None
        self._last_result = result
        # Les workouts réussis sont décochés ; les échoués restent cochés pour
        # réessayer (UX parcours C).
        if succeeded_ids:
            self._selected -= set(succeeded_ids)
            self._notify_selection_changed()
        on_done(result)
        self._notify_sending_state_changed()

    def _on_push_failure(self, on_error, exc) -> None:
        self._is_sending = False
        self._progress = None
        on_error(exc)
        self._notify_sending_state_changed()

    # -- internes de notification -------------------------------------------

    def _notify_workouts_changed(self) -> None:
        if self._on_workouts_changed_cb is not None:
            self._on_workouts_changed_cb()

    def _notify_selection_changed(self) -> None:
        if self._on_selection_changed_cb is not None:
            self._on_selection_changed_cb()

    def _notify_sending_state_changed(self) -> None:
        if self._on_sending_state_changed_cb is not None:
            self._on_sending_state_changed_cb()
