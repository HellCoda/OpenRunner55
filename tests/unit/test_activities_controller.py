"""Tests unitaires du `ActivitiesController` (logique de présentation sans GTK).

Voir docs/decisions/adr-008.md (stratégie de test) et le brief
`docs/dev/Epic-3-brief-frontend.md` (contrat du controller).

Le controller est testé avec des doublures de ses dépendances Core
(`GarminClient`, `WatchFilesystem`, `TransferredFilesStore`, `SyncHistoryStore`,
`OperationLogger`, `WatchDetector`) et un scheduler synchrone (défaut) pour
observer l'état sans boucle GTK. Les services réels `list_uploadable_files` /
`push_activities` sont exercés sur les doublures (pattern Epic 2,
`test_workouts_controller.py`). Les callbacks async s'exécutent dans le thread
worker ; les tests attendent la fin via un `threading.Event`.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from openrunner55.sync.activities import UploadableFile
from openrunner55.ui.activities_controller import ActivitiesController


# --- Doublures ---------------------------------------------------------------


def _uf(
    name: str,
    category: str = "Activity",
    transferred: bool = False,
    size: int = 100,
) -> UploadableFile:
    """Construit un `UploadableFile` de test (chemin relatif à GARMIN/)."""
    return UploadableFile(
        path=Path(f"{category}/{name}.fit"),
        category=category.lower(),
        size=size,
        already_transferred=transferred,
    )


class FakeWatch:
    """Doublure de WatchFilesystem : listing pilotable, chemins absolus faux."""

    def __init__(self, files_by_category: dict[str, list[Path]] | None = None):
        self.files_by_category = files_by_category or {}
        self.list_calls = 0
        self.fail: Exception | None = None
        self.block: tuple[threading.Event, threading.Event] | None = None

    def list_fit_files(self, category: str) -> list[Path]:
        self.list_calls += 1
        if self.fail is not None:
            raise self.fail
        if self.block is not None:
            started, release = self.block
            started.set()
            release.wait(timeout=1)
        return list(self.files_by_category.get(category, []))

    def file_size(self, path: Path) -> int:
        return 100

    def absolute_path(self, path: Path) -> Path:
        return Path("/mnt/GARMIN/GARMIN") / path


class FakeTransfers:
    """Doublure de TransferredFilesStore : dédup en mémoire."""

    def __init__(self, transferred: set[str] | None = None):
        self.transferred = set(transferred or ())
        self.marked: list[tuple] = []

    def is_transferred(self, file_name, direction, source) -> bool:
        return file_name in self.transferred

    def mark_transferred(self, file_name, direction, source, gc_activity_id=None) -> None:
        self.transferred.add(file_name)
        self.marked.append((file_name, direction, source))


class FakeClient:
    """Doublure de GarminClient : `upload_activity` pilotable."""

    def __init__(self, fail_names: set[str] | None = None):
        self.uploaded: list[Path] = []
        self.fail_names = set(fail_names or ())
        self.block: tuple[threading.Event, threading.Event] | None = None

    def upload_activity(self, path: Path) -> None:
        if self.block is not None:
            started, release = self.block
            started.set()
            release.wait(timeout=1)
        if path.name in self.fail_names:
            raise RuntimeError("GC a rejeté le fichier")
        self.uploaded.append(path)


class FakeHistory:
    def __init__(self):
        self.logs: list[tuple] = []

    def log_sync(self, direction, file_count, status, details=None) -> None:
        self.logs.append((direction, file_count, status, details))


class FakeLogger:
    def __init__(self):
        self.logs: list[tuple] = []

    def log(self, operation, status, message) -> None:
        self.logs.append((operation, status, message))


class FakeDetector:
    """Doublure de WatchDetector : état de connexion pilotable."""

    def __init__(self, connected: bool = True, mount_path: Path | None = None):
        self._connected = connected
        self._mount_path = mount_path if connected else None
        self.callbacks: list = []

    def is_connected(self) -> bool:
        return self._connected

    def get_mount_path(self) -> Path | None:
        return self._mount_path

    def on_status_changed(self, callback) -> None:
        self.callbacks.append(callback)

    def set_connected(self, connected: bool, mount_path: Path | None = None) -> None:
        self._connected = connected
        self._mount_path = mount_path if connected else None


# --- Fabrique de controller ---------------------------------------------------


def _make_controller(
    client: FakeClient | None = None,
    watch: FakeWatch | None = None,
    transfers: FakeTransfers | None = None,
    detector: FakeDetector | None = None,
) -> ActivitiesController:
    """Construit un controller avec des doublures et un scheduler synchrone."""
    client = client or FakeClient()
    watch = watch or FakeWatch()
    transfers = transfers or FakeTransfers()
    detector = detector or FakeDetector(connected=True, mount_path=Path("/mnt/GARMIN"))
    return ActivitiesController(
        client=client,
        watch_factory=lambda mount_path: watch,
        transfers=transfers,
        history=FakeHistory(),
        logger=FakeLogger(),
        detector=detector,
        # scheduler par défaut : synchrone
    )


def _await(event: threading.Event, timeout: float = 1.0) -> None:
    assert event.wait(timeout=timeout), "opération async non terminée à temps"


def _wait_until(predicate, timeout: float = 1.0) -> None:
    """Attend une condition évaluée depuis le thread du worker (poll léger)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail("condition non atteinte à temps")


# --- État de la liste --------------------------------------------------------


@pytest.mark.unit
class TestListState:
    def test_list_updates_files_and_clears_loading(self) -> None:
        f1, f2 = _uf("a"), _uf("b")
        watch = FakeWatch({"Activity": [f1.path, f2.path]})
        controller = _make_controller(watch=watch)
        done = threading.Event()
        results: list = []

        controller.list_uploadable_files_async(
            on_done=lambda files: (results.append(files), done.set()),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert [f.path for f in controller.files] == [f1.path, f2.path]
        assert controller.is_loading is False
        assert len(results) == 1

    def test_is_loading_true_during(self) -> None:
        f = _uf("a")
        watch = FakeWatch({"Activity": [f.path]})
        started, release = threading.Event(), threading.Event()
        watch.block = (started, release)
        controller = _make_controller(watch=watch)
        done = threading.Event()

        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(), on_error=lambda e: done.set()
        )
        assert started.wait(timeout=1)
        assert controller.is_loading is True
        release.set()
        _await(done)
        assert controller.is_loading is False

    def test_fires_files_changed(self) -> None:
        controller = _make_controller()
        events: list = []
        controller.on_files_changed(lambda: events.append("changed"))
        done = threading.Event()

        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(), on_error=lambda e: done.set()
        )
        _await(done)
        # notifié au démarrage (loading) puis à la fin (résultat)
        assert len(events) >= 2

    def test_error_clears_loading_and_calls_on_error(self) -> None:
        watch = FakeWatch()
        watch.fail = OSError("lecture GARMIN/ KO")
        controller = _make_controller(watch=watch)
        done = threading.Event()
        errors: list = []

        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(),
            on_error=lambda e: (errors.append(e), done.set()),
        )
        _await(done)

        assert len(errors) == 1
        assert controller.is_loading is False
        assert controller.files == []

    def test_launch_deferred_until_watch_connected(self) -> None:
        f = _uf("a")
        watch = FakeWatch({"Activity": [f.path]})
        detector = FakeDetector(connected=False)
        controller = _make_controller(watch=watch, detector=detector)
        done = threading.Event()

        # Montre déconnectée : rien ne se lance, les callbacks sont mémorisés.
        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(), on_error=lambda e: done.set()
        )
        assert controller.is_loading is False
        assert watch.list_calls == 0

        # Branchement : le listing se déclenche automatiquement.
        detector.set_connected(True, mount_path=Path("/mnt/GARMIN"))
        controller.on_watch_status_changed(True)
        _await(done)
        assert [uf.path for uf in controller.files] == [f.path]

    def test_no_reentrant_launch(self) -> None:
        f = _uf("a")
        watch = FakeWatch({"Activity": [f.path]})
        started, release = threading.Event(), threading.Event()
        watch.block = (started, release)
        controller = _make_controller(watch=watch)

        controller.list_uploadable_files_async(
            on_done=lambda files: None, on_error=lambda e: None
        )
        assert started.wait(timeout=1)
        # Second appel pendant le chargement : lancement ignoré (garde
        # is_loading). NB : les callbacks sont quand même mémorisés
        # (dernier enregistré gagne) — seul le LANCEMENT est gardé.
        controller.list_uploadable_files_async(
            on_done=lambda files: None, on_error=lambda e: None
        )
        controller.on_watch_status_changed(True)  # re-branchement simulé
        release.set()
        _wait_until(lambda: controller.is_loading is False)
        # Une seule série de listings (4 catégories), pas de re-entrée.
        assert watch.list_calls == 4
        assert [uf.path for uf in controller.files] == [f.path]


# --- Pré-sélection automatique -----------------------------------------------


@pytest.mark.unit
class TestPreselection:
    def test_after_list_only_new_files_selected(self) -> None:
        new, old = _uf("nouveau"), _uf("deja_la")
        watch = FakeWatch({"Activity": [new.path, old.path]})
        transfers = FakeTransfers(transferred={"deja_la.fit"})
        controller = _make_controller(watch=watch, transfers=transfers)
        selection_events: list = []
        controller.on_selection_changed(lambda: selection_events.append("x"))
        done = threading.Event()

        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(), on_error=lambda e: done.set()
        )
        _await(done)

        assert controller.selected == {new.path}
        assert selection_events  # callback déclenché

    def test_after_list_all_transferred_selection_empty(self) -> None:
        old = _uf("deja_la")
        watch = FakeWatch({"Activity": [old.path]})
        transfers = FakeTransfers(transferred={"deja_la.fit"})
        controller = _make_controller(watch=watch, transfers=transfers)
        done = threading.Event()

        controller.list_uploadable_files_async(
            on_done=lambda files: done.set(), on_error=lambda e: done.set()
        )
        _await(done)

        assert controller.selected == set()


# --- Sélection ----------------------------------------------------------------


@pytest.mark.unit
class TestSelection:
    def _controller_with_files(self, *files: UploadableFile) -> ActivitiesController:
        controller = _make_controller()
        controller._files = list(files)
        return controller

    def test_toggle_adds_and_removes(self) -> None:
        f = _uf("a")
        controller = self._controller_with_files(f)
        events: list = []
        controller.on_selection_changed(lambda: events.append("x"))

        controller.toggle_selection(f.path)
        assert controller.selected == {f.path}
        controller.toggle_selection(f.path)
        assert controller.selected == set()
        assert len(events) == 2

    def test_selected_count(self) -> None:
        f1, f2 = _uf("a"), _uf("b")
        controller = self._controller_with_files(f1, f2)
        controller.toggle_selection(f1.path)
        controller.toggle_selection(f2.path)
        assert controller.selected_count == 2
        controller.toggle_selection(f2.path)
        assert controller.selected_count == 1

    def test_select_all_includes_transferred(self) -> None:
        f_new, f_old = _uf("a"), _uf("b", transferred=True)
        controller = self._controller_with_files(f_new, f_old)
        controller.select_all()
        assert controller.selected == {f_new.path, f_old.path}

    def test_select_new_only_excludes_transferred(self) -> None:
        f_new, f_old = _uf("a"), _uf("b", transferred=True)
        controller = self._controller_with_files(f_new, f_old)
        controller.select_all()
        controller.select_new_only()
        assert controller.selected == {f_new.path}

    def test_select_none(self) -> None:
        f = _uf("a")
        controller = self._controller_with_files(f)
        controller.select_all()
        controller.select_none()
        assert controller.selected == set()


# --- Activation du bouton synchroniser ----------------------------------------


@pytest.mark.unit
class TestCanSync:
    def _controller_with_selection(
        self, watch: FakeWatch | None = None, client: FakeClient | None = None
    ) -> tuple[ActivitiesController, UploadableFile]:
        f = _uf("a")
        detector = FakeDetector(connected=True, mount_path=Path("/mnt/GARMIN"))
        controller = _make_controller(
            watch=watch, client=client, detector=detector
        )
        controller._files = [f]
        controller.toggle_selection(f.path)
        return controller, f

    def test_true_when_ready(self) -> None:
        controller, _ = self._controller_with_selection()
        assert controller.can_sync is True

    def test_false_when_selection_empty(self) -> None:
        controller, f = self._controller_with_selection()
        controller.toggle_selection(f.path)
        assert controller.can_sync is False

    def test_false_when_watch_disconnected(self) -> None:
        controller, _ = self._controller_with_selection()
        controller.on_watch_status_changed(False)
        assert controller.can_sync is False

    def test_false_while_loading(self) -> None:
        watch = FakeWatch()
        started, release = threading.Event(), threading.Event()
        watch.block = (started, release)
        controller, _ = self._controller_with_selection(watch=watch)

        controller.list_uploadable_files_async(
            on_done=lambda files: None, on_error=lambda e: None
        )
        assert started.wait(timeout=1)
        assert controller.is_loading is True
        assert controller.can_sync is False
        release.set()
        _wait_until(lambda: controller.is_loading is False)

    def test_false_while_sending(self) -> None:
        client = FakeClient()
        started, release = threading.Event(), threading.Event()
        client.block = (started, release)
        controller, _ = self._controller_with_selection(client=client)

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: None,
            on_error=lambda e: None,
        )
        assert started.wait(timeout=1)
        assert controller.is_sending is True
        assert controller.can_sync is False
        release.set()
        _wait_until(lambda: controller.is_sending is False)


# --- Envoi ---------------------------------------------------------------------


@pytest.mark.unit
class TestPush:
    def _controller(self, files, client=None, transfers=None):
        detector = FakeDetector(connected=True, mount_path=Path("/mnt/GARMIN"))
        controller = _make_controller(
            client=client or FakeClient(), transfers=transfers, detector=detector
        )
        controller._files = list(files)
        return controller

    def test_items_are_selected_uploadable_files(self) -> None:
        f1, f2, f3 = _uf("a"), _uf("b"), _uf("c")
        client = FakeClient()
        controller = self._controller([f1, f2, f3], client=client)
        controller.toggle_selection(f1.path)
        controller.toggle_selection(f3.path)  # f2 non sélectionné
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert {p.name for p in client.uploaded} == {"a.fit", "c.fit"}

    def test_progress_before_each_file_and_done_result(self) -> None:
        f1, f2 = _uf("a"), _uf("b")
        controller = self._controller([f1, f2])
        controller.select_all()
        progress: list = []
        results: list = []
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda c, t, n: progress.append((c, t, n)),
            on_done=lambda r: (results.append(r), done.set()),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert progress == [(1, 2, "a.fit"), (2, 2, "b.fit")]
        assert len(results) == 1
        assert results[0].total == 2
        assert results[0].success == 2
        assert controller.progress is None

    def test_is_sending_true_during_false_after(self) -> None:
        f = _uf("a")
        client = FakeClient()
        started, release = threading.Event(), threading.Event()
        client.block = (started, release)
        controller = self._controller([f], client=client)
        controller.toggle_selection(f.path)
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        assert started.wait(timeout=1)
        assert controller.is_sending is True
        release.set()
        _await(done)
        assert controller.is_sending is False

    def test_selection_after_push_success_fail_skip(self) -> None:
        # Le skip au push dépend du drapeau already_transferred porté par
        # l'objet UploadableFile (foi du backend), pas du store.
        ok, ko, skip = _uf("ok"), _uf("ko"), _uf("skip", transferred=True)
        client = FakeClient(fail_names={"ko.fit"})
        transfers = FakeTransfers()
        controller = self._controller([ok, ko, skip], client=client, transfers=transfers)
        controller.select_all()
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        result = controller.last_result
        assert result is not None
        assert (result.total, result.success, result.failed, result.skipped) == (
            3,
            1,
            1,
            1,
        )
        assert len(result.errors) == 1
        assert "file Activity/ko.fit" in result.errors[0]
        # échoué reste coché ; envoyés et skippés décochés
        assert controller.selected == {ko.path}

    def test_already_transferred_skipped_without_api_call(self) -> None:
        old = _uf("deja_la", transferred=True)
        client = FakeClient()
        controller = self._controller([old], client=client)
        controller.toggle_selection(old.path)
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert client.uploaded == []
        assert controller.last_result.skipped == 1
        assert controller.last_result.success == 0

    def test_successful_file_marked_transferred_locally(self) -> None:
        f = _uf("a")
        controller = self._controller([f])
        controller.toggle_selection(f.path)
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        # reflet local du store : la ligne se grise sans re-listing
        assert controller.files[0].already_transferred is True

    def test_fatal_error_when_mount_gone_before_push(self) -> None:
        f = _uf("a")
        detector = FakeDetector(connected=True, mount_path=Path("/mnt/GARMIN"))
        controller = _make_controller(detector=detector)
        controller._files = [f]
        controller.toggle_selection(f.path)
        detector._mount_path = None  # débranchée juste après l'activation
        done = threading.Event()
        errors: list = []

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: (errors.append(e), done.set()),
        )
        _await(done)

        assert len(errors) == 1
        assert controller.is_sending is False
        assert controller.progress is None

    def test_push_with_empty_selection_does_nothing(self) -> None:
        controller = self._controller([_uf("a")])
        called = threading.Event()
        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: called.set(),
            on_error=lambda e: called.set(),
        )
        assert not called.wait(timeout=0.1)
        assert controller.is_sending is False


# --- Skipped (contrat SyncResult) ----------------------------------------------


@pytest.mark.unit
class TestSkippedExposed:
    def test_last_result_carries_skipped_count(self) -> None:
        old = _uf("deja_la", transferred=True)
        controller = _make_controller()
        controller._files = [old]
        controller.toggle_selection(old.path)
        done = threading.Event()

        controller.push_activities_async(
            on_progress=lambda *a: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert controller.last_result is not None
        assert controller.last_result.skipped == 1  # le controller n'écrase pas


# --- Statut montre ---------------------------------------------------------------


@pytest.mark.unit
class TestWatchStatus:
    def test_disconnect_clears_files_selection_and_can_sync(self) -> None:
        f = _uf("a")
        controller = _make_controller()
        controller._files = [f]
        controller.toggle_selection(f.path)
        assert controller.can_sync is True

        controller.on_watch_status_changed(False)

        assert controller.files == []
        assert controller.selected == set()
        assert controller.can_sync is False

    def test_stale_list_result_discarded_on_disconnect(self) -> None:
        f = _uf("a")
        watch = FakeWatch({"Activity": [f.path]})
        started, release = threading.Event(), threading.Event()
        watch.block = (started, release)
        controller = _make_controller(watch=watch)
        files_events: list = []
        controller.on_files_changed(lambda: files_events.append("x"))

        controller.list_uploadable_files_async(
            on_done=lambda files: None, on_error=lambda e: None
        )
        assert started.wait(timeout=1)
        controller.on_watch_status_changed(False)  # débranchée pendant le chargement
        release.set()
        _wait_until(lambda: len(files_events) >= 3)

        assert controller.files == []
        assert controller.is_loading is False

    def test_watch_status_signal_from_detector(self) -> None:
        detector = FakeDetector(connected=False)
        controller = _make_controller(detector=detector)
        assert controller.watch_connected is False
        # Le controller s'est abonné au signal du détecteur à la construction
        # (méthode liée : `==` compare fonction + instance).
        assert any(
            cb == controller.on_watch_status_changed for cb in detector.callbacks
        )
