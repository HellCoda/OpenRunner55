"""Logique de présentation de la zone Montre (couche UI, sans GTK).

`ActivitiesController` extrait de la vue GTK toute la logique testable
unitairement pour le sens **Montre → Garmin Connect** (Epic 3) : état de la
liste des fichiers .FIT, sélection, pré-sélection des fichiers nouveaux,
activation du bouton « Synchroniser », état du transfert. Il ne touche jamais
aux widgets — il expose un état et des callbacks ; la vue s'abonne et
rafraîchit l'interface quand un callback est déclenché (pattern observateur,
miroir de `WorkoutsController`).

Contraintes d'architecture (ADR-002) :

- **Pas d'import de `gi.repository`** : le controller est testable avec des
  doublures, sans boucle GTK.
- **Pas d'import des modules Core** (`garmin/`, `watch/`, `store/`) à
  l'exécution : les dépendances Core sont injectées (duck-typing) et leurs
  types ne sont référencés que sous `TYPE_CHECKING` (annotations seulement).
- **Toute la logique métier vient du Service** `sync/activities.py`
  (`list_uploadable_files`, `push_activities`) : pas de filtrage, pas de tri,
  pas de dédup réimplémentés ici.

Threading (brief Epic 3, option A — identique à l'Epic 2) :

- `list_uploadable_files_async` et `push_activities_async` lancent un thread
  daemon ; le travail réseau/USB s'exécute hors du thread GTK.
- Les callbacks vers l'état sont marshallés via un *scheduler* injectable. En
  production la vue passe `GLib.idle_add` ; dans les tests on utilise le
  scheduler synchrone par défaut (invocation immédiate, observable sans
  boucle GTK).

Décisions de conception (documentées, cf. notes de dev Epic 3) :

- **Progression par fichier** : le contrat figé `push_activities(items) ->
  SyncResult` n'expose aucun callback de progression. Le worker boucle donc
  sur `push_activities([item])` par fichier et agrège les bilans — pattern
  exact de `WorkoutsController._push_worker`. Seule façon d'émettre
  `on_progress(current, total, name)` avant chaque fichier.
- **Sort de la sélection après envoi** (grâce à la boucle unitaire) : fichiers
  envoyés et skippés (déjà transférés) décochés ; fichiers échoués **restent
  cochés** pour réessayer (UX parcours C).
- **Listing différé au branchement** : `list_uploadable_files_async` mémorise
  les callbacks de la vue. Si la montre est déconnectée, le lancement est
  différé ; `on_watch_status_changed(True)` le déclenche alors (une seule
  fois, garde `is_loading`). La vue n'a pas à s'abonner au détecteur.
- **Pré-sélection automatique** : après un listing réussi, seuls les fichiers
  `already_transferred=False` sont sélectionnés (décision de cadrage « UX de
  la première sync » du brief).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from openrunner55.sync.activities import (
    SyncResult,
    UploadableFile,
    list_uploadable_files,
    push_activities,
)
from openrunner55.ui.workouts_controller import WatchNotConnectedError

if TYPE_CHECKING:
    from openrunner55.garmin.client import GarminClient
    from openrunner55.store.history import SyncHistoryStore
    from openrunner55.store.logger import OperationLogger
    from openrunner55.store.transfers import TransferredFilesStore
    from openrunner55.watch.detector import WatchDetector
    from openrunner55.watch.filesystem import WatchFilesystem


def _direct_scheduler(callback: Callable[..., None], *args: Any) -> None:
    """Scheduler synchrone par défaut : invoque le callback immédiatement.

    Utilisé dans les tests pour observer l'état sans boucle GTK. En production,
    la vue injecte `GLib.idle_add` pour marshaller les callbacks vers le thread
    GTK principal.
    """
    callback(*args)


def _noop(*_args: Any) -> None:
    """Callback vide — pour les lancements automatiques sans notifieur."""


class ActivitiesController:
    """Logique de présentation de la zone Montre (testable sans GTK).

    :param client: client Garmin authentifié (injecté, duck-typed).
    :param watch_factory: construit un `WatchFilesystem` frais depuis un point
        de montage (`Callable[[Path], WatchFilesystem]`). Le point de montage
        est dynamique (il change à chaque branchement) — la factory le résout
        au moment de l'action, sans import Core dans le controller.
    :param transfers: store des fichiers transférés (injecté).
    :param history: store de l'historique de sync (injecté).
    :param logger: logger d'opérations (injecté).
    :param detector: détecteur USB de la montre (Core exposé comme service,
        validé par le DP depuis l'Epic 2). Partagé avec `WorkoutsController`.
    :param scheduler: marshallage des callbacks vers le thread GTK
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
        self._files: list[UploadableFile] = []
        self._is_loading = False
        self._selected: set[Path] = set()
        self._is_sending = False
        self._progress: tuple[int, int, str] | None = None
        self._last_result: SyncResult | None = None
        self._watch_connected: bool = detector.is_connected()

        # -- callbacks de la vue (pattern observateur) --
        self._on_files_changed_cb: Callable[[], None] | None = None
        self._on_selection_changed_cb: Callable[[], None] | None = None
        self._on_sending_state_changed_cb: Callable[[], None] | None = None

        # -- callbacks par-appel du listing (mémorisés pour le lancement
        #    différé au branchement, cf. docstring du module) --
        self._list_on_done: Callable[[list[UploadableFile]], None] = _noop
        self._list_on_error: Callable[[Exception], None] = _noop

        # Branché au signal de détection partagé (même instance que
        # WorkoutsController — chaque controller s'y abonne indépendamment).
        detector.on_status_changed(self.on_watch_status_changed)

    # -- état de la liste ----------------------------------------------------

    @property
    def files(self) -> list[UploadableFile]:
        """Liste des fichiers uploadables affichés (copie défensive)."""
        return list(self._files)

    @property
    def is_loading(self) -> bool:
        """True pendant le chargement de la liste (`list_uploadable_files`)."""
        return self._is_loading

    # -- sélection -----------------------------------------------------------

    @property
    def selected(self) -> set[Path]:
        """Ensemble des chemins relatifs sélectionnés (copie défensive)."""
        return set(self._selected)

    def toggle_selection(self, path: Path) -> None:
        """Ajoute ou retire un fichier de la sélection."""
        if path in self._selected:
            self._selected.discard(path)
        else:
            self._selected.add(path)
        self._notify_selection_changed()

    def select_all(self) -> None:
        """Sélectionne tous les fichiers listés (y compris déjà transférés).

        Les déjà transférés seront skippés par `push_activities` sans appel
        API (délai 3 s évité, cf. décision de cadrage du brief).
        """
        self._selected = {f.path for f in self._files}
        self._notify_selection_changed()

    def select_new_only(self) -> None:
        """Sélectionne uniquement les fichiers non encore transférés."""
        self._selected = {f.path for f in self._files if not f.already_transferred}
        self._notify_selection_changed()

    def select_none(self) -> None:
        """Désélectionne tout."""
        self._selected.clear()
        self._notify_selection_changed()

    @property
    def selected_count(self) -> int:
        """Nombre de fichiers sélectionnés (pour « Synchroniser (N) »)."""
        return len(self._selected)

    # -- état de la montre ---------------------------------------------------

    @property
    def watch_connected(self) -> bool:
        """True si la montre est détectée comme connectée (état suivi)."""
        return self._watch_connected

    # -- activation du bouton synchroniser ----------------------------------

    @property
    def can_sync(self) -> bool:
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
        """True pendant un envoi vers Garmin Connect."""
        return self._is_sending

    @property
    def progress(self) -> tuple[int, int, str] | None:
        """`(current, total, current_file_name)` ou None si pas en cours."""
        return self._progress

    @property
    def last_result(self) -> SyncResult | None:
        """Dernier `SyncResult` d'un envoi, ou None si aucun envoi terminé."""
        return self._last_result

    # -- callbacks de la vue (à connecter) ----------------------------------

    def on_files_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand la liste ou le chargement change."""
        self._on_files_changed_cb = callback

    def on_selection_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand la sélection change."""
        self._on_selection_changed_cb = callback

    def on_sending_state_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand l'état du transfert change."""
        self._on_sending_state_changed_cb = callback

    def on_watch_status_changed(self, connected: bool) -> None:
        """Branché au signal `WatchDetector.on_status_changed`.

        - Au branchement (`True`) : déclenche le listing (immédiat ou différé
          mémorisé par `list_uploadable_files_async`) — une seule fois, garde
          `is_loading` anti-re-entrante.
        - Au débranchement (`False`) : vide la liste et la sélection (la zone
          Montre retombe sur le placeholder « Branchez votre montre »).
        """
        self._watch_connected = connected
        if connected:
            self.list_uploadable_files_async(self._list_on_done, self._list_on_error)
        else:
            self._files = []
            self._selected = set()
            self._notify_files_changed()
            self._notify_selection_changed()
        self._notify_sending_state_changed()

    # -- actions asynchrones ------------------------------------------------

    def list_uploadable_files_async(
        self,
        on_done: Callable[[list[UploadableFile]], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Charge la liste des fichiers .FIT dans un thread dédié (hors GTK).

        Les callbacks sont mémorisés : si la montre est déconnectée au moment
        de l'appel, le lancement est **différé** au prochain branchement (cf.
        docstring du module). Aucun lancement si un chargement est déjà en
        cours (garde anti-re-entrante).

        :param on_done: appelé (thread GTK) avec la liste des fichiers.
        :param on_error: appelé (thread GTK) en cas d'échec du listing.
        """
        self._list_on_done = on_done
        self._list_on_error = on_error
        if not self._watch_connected or self._is_loading:
            return
        self._is_loading = True
        self._notify_files_changed()
        threading.Thread(target=self._list_worker, daemon=True).start()

    def push_activities_async(
        self,
        on_progress: Callable[[int, int, str], None],
        on_done: Callable[[SyncResult], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        """Envoie les fichiers sélectionnés vers Garmin Connect (thread dédié).

        :param on_progress: appelé (thread GTK) avant chaque fichier avec
            `(current, total, name)`.
        :param on_done: appelé (thread GTK) avec le `SyncResult` agrégé.
        :param on_error: appelé (thread GTK) en cas d'erreur fatale (ex. montre
            débranchée avant le premier upload). Les échecs par fichier sont
            déjà gérés par `push_activities` via `SyncResult.errors`.
        """
        if self._is_sending:
            return
        items = [f for f in self._files if f.path in self._selected]
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

    # -- workers (thread secondaire) ----------------------------------------

    def _list_worker(self) -> None:
        try:
            files = list_uploadable_files(self._make_watch(), self._transfers)
            self._scheduler(self._on_list_success, files)
        except Exception as exc:  # noqa: BLE001 - erreur fatale remontée à la vue
            self._scheduler(self._on_list_failure, exc)

    def _push_worker(
        self, items, on_progress, on_done, on_error
    ) -> None:
        try:
            watch = self._make_watch()
            total = len(items)
            success = 0
            failed = 0
            skipped = 0
            errors: list[str] = []
            uncheck_paths: set[Path] = set()
            succeeded_paths: list[Path] = []
            for current, item in enumerate(items, start=1):
                # Progression « avant chaque fichier », marshallée vers le GTK.
                self._scheduler(
                    self._apply_progress, on_progress, current, total, item.path.name
                )
                result = push_activities(
                    self._client,
                    watch,
                    self._transfers,
                    self._history,
                    self._logger,
                    [item],
                )
                total_i = result.total
                success += result.success
                failed += result.failed
                skipped += result.skipped
                errors.extend(result.errors)
                assert total_i == 1  # contrat : un appel unitaire, un fichier
                if result.success:
                    succeeded_paths.append(item.path)
                    uncheck_paths.add(item.path)
                elif result.skipped:
                    # Déjà transféré : décoché (déjà validé côté GC).
                    uncheck_paths.add(item.path)
                # Échoué : reste coché pour réessayer (UX parcours C).

            final = SyncResult(
                total=total,
                success=success,
                failed=failed,
                errors=errors,
                skipped=skipped,
            )
            self._scheduler(
                self._on_push_success, on_done, final, uncheck_paths, succeeded_paths
            )
        except Exception as exc:  # noqa: BLE001 - erreur fatale remontée à la vue
            self._scheduler(self._on_push_failure, on_error, exc)

    def _make_watch(self) -> WatchFilesystem:
        """Résout le point de montage courant et construit un filesystem frais.

        :raises WatchNotConnectedError: si la montre est débranchée (point de
            montage indisponible) avant le début de l'opération.
        """
        mount_path = self._detector.get_mount_path()
        if mount_path is None:
            raise WatchNotConnectedError(
                "La montre a été débranchée avant le début de l'opération."
            )
        return self._watch_factory(mount_path)

    # -- handlers (thread GTK via le scheduler) ------------------------------

    def _on_list_success(self, files: list[UploadableFile]) -> None:
        self._is_loading = False
        if not self._watch_connected:
            # Montre débranchée pendant le chargement : résultat périmé,
            # la liste est déjà vidée par on_watch_status_changed(False).
            self._notify_files_changed()
            return
        self._files = files
        # Pré-sélection des fichiers nouveaux (décision de cadrage « UX de la
        # première sync ») : seuls les non transférés sont cochés à l'affichage.
        self._selected = {f.path for f in files if not f.already_transferred}
        self._notify_selection_changed()
        self._list_on_done(files)
        self._notify_files_changed()

    def _on_list_failure(self, exc: Exception) -> None:
        self._is_loading = False
        self._list_on_error(exc)
        self._notify_files_changed()

    def _apply_progress(
        self,
        on_progress: Callable[[int, int, str], None],
        current: int,
        total: int,
        name: str,
    ) -> None:
        self._progress = (current, total, name)
        self._notify_sending_state_changed()
        on_progress(current, total, name)

    def _on_push_success(
        self,
        on_done: Callable[[SyncResult], None],
        result: SyncResult,
        uncheck_paths: set[Path],
        succeeded_paths: list[Path],
    ) -> None:
        self._is_sending = False
        self._progress = None
        self._last_result = result
        # Reflet local du store : les fichiers uploadés avec succès sont
        # marqués « déjà transférés » dans la liste (la ligne se grise sans
        # re-listing). Le backend a déjà écrit en SQLite via push_activities.
        if succeeded_paths:
            succeeded = set(succeeded_paths)
            for f in self._files:
                if f.path in succeeded:
                    f.already_transferred = True
            self._notify_files_changed()
        # Envoyés et skippés décochés ; échoués restent cochés (UX parcours C).
        if uncheck_paths:
            self._selected -= uncheck_paths
            self._notify_selection_changed()
        on_done(result)
        self._notify_sending_state_changed()

    def _on_push_failure(self, on_error: Callable[[Exception], None], exc: Exception) -> None:
        self._is_sending = False
        self._progress = None
        # Notifier l'état AVANT on_error : la vue rafraîchit d'abord avec l'état
        # nettoyé (last_result inchangé), puis on_error écrit le message d'erreur
        # en dernier — sinon _update_watch_summary masque le message écrit par
        # _on_watch_push_error (last_result is None → label caché).
        self._notify_sending_state_changed()
        on_error(exc)

    # -- internes de notification -------------------------------------------

    def _notify_files_changed(self) -> None:
        if self._on_files_changed_cb is not None:
            self._on_files_changed_cb()

    def _notify_selection_changed(self) -> None:
        if self._on_selection_changed_cb is not None:
            self._on_selection_changed_cb()

    def _notify_sending_state_changed(self) -> None:
        if self._on_sending_state_changed_cb is not None:
            self._on_sending_state_changed_cb()
