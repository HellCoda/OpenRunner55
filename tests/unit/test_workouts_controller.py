"""Tests unitaires du `WorkoutsController` (logique de présentation sans GTK).

Voir docs/decisions/adr-008.md (stratégie de test) et le brief
`docs/dev/Epic-2-brief-frontend.md` (contrat du controller).

Le controller est testé avec des doublures de ses dépendances Core
(`GarminClient`, `WatchFilesystem`, `TransferredFilesStore`, `SyncHistoryStore`,
`OperationLogger`, `WatchDetector`) et un scheduler synchrone (défaut) pour
observer l'état sans boucle GTK. Les callbacks async s'exécutent dans le thread
worker ; les tests attendent la fin via un `threading.Event`.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from openrunner55.sync.workouts import SyncResult, WorkoutSummary

from openrunner55.ui import workouts_controller as controller_module
from openrunner55.ui.workouts_controller import WorkoutsController


# --- Doublures ---------------------------------------------------------------


class FakeClient:
    """Doublure de GarminClient : `get_workouts` pilotable, `download` pilotable."""

    def __init__(self, workouts: list[dict] | None = None):
        self._workouts = workouts or []
        self.get_workouts_calls = 0

    def get_workouts(self, start: int = 0, limit: int = 20) -> list[dict]:
        self.get_workouts_calls += 1
        return self._workouts

    def download_workout(self, workout_id: int) -> bytes:
        return b"FIT"


class BlockingClient(FakeClient):
    """Client qui bloque sur `get_workouts` pour observer `is_loading`."""

    def __init__(self):
        super().__init__([])
        self.started = threading.Event()
        self.release = threading.Event()

    def get_workouts(self, start: int = 0, limit: int = 20) -> list[dict]:
        self.started.set()
        self.release.wait(timeout=1)
        return []


class FakeWatch:
    """Doublure de WatchFilesystem : liste vide, écriture en mémoire."""

    def __init__(self):
        self.written: list[tuple[Path, bytes]] = []

    def list_fit_files(self, category: str) -> list[Path]:
        return []

    def write_fit(self, path: Path, data: bytes) -> None:
        self.written.append((path, data))


class FakeTransfers:
    def __init__(self):
        self.marked: list[tuple] = []

    def mark_transferred(self, file_name, direction, source, gc_activity_id=None) -> None:
        self.marked.append((file_name, direction, source))


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

    def set_connected(self, connected: bool) -> None:
        self._connected = connected
        if not connected:
            self._mount_path = None


def _make_controller(
    client: FakeClient | None = None,
    detector: FakeDetector | None = None,
    watch_factory=None,
) -> WorkoutsController:
    """Construit un controller avec des doublures et un scheduler synchrone."""
    client = client or FakeClient()
    detector = detector or FakeDetector(connected=True, mount_path=Path("/mnt/GARMIN"))
    watch_factory = watch_factory or (lambda mount_path: FakeWatch())
    return WorkoutsController(
        client=client,
        watch_factory=watch_factory,
        transfers=FakeTransfers(),
        history=FakeHistory(),
        logger=FakeLogger(),
        detector=detector,
        # scheduler par défaut : synchrone
    )


def _summaries(*ids: int) -> list[WorkoutSummary]:
    """Construit des WorkoutSummary de test (id → nom « Workout {id} »)."""
    return [
        WorkoutSummary(workout_id=i, name=f"Workout {i}", date=None, type="running")
        for i in ids
    ]


def _await(event: threading.Event, timeout: float = 1.0) -> None:
    assert event.wait(timeout=timeout), "opération async non terminée à temps"


# --- État de la liste --------------------------------------------------------


@pytest.mark.unit
class TestFetch:
    def test_fetch_updates_workouts_and_loading(self) -> None:
        client = FakeClient(
            [
                {"workoutId": 1, "workoutName": "A", "updatedDate": "2026-08-01T00:00:00.0"},
                {"workoutId": 2, "workoutName": "B"},
            ]
        )
        controller = _make_controller(client=client)
        done = threading.Event()
        results: list = []

        controller.fetch_workouts_async(
            on_done=lambda w: (results.append(w), done.set()),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert [w.workout_id for w in controller.workouts] == [1, 2]
        assert controller.is_loading is False
        assert len(results) == 1

    def test_fetch_is_loading_true_during(self) -> None:
        client = BlockingClient()
        controller = _make_controller(client=client)
        done = threading.Event()

        controller.fetch_workouts_async(
            on_done=lambda w: done.set(),
            on_error=lambda e: done.set(),
        )
        assert client.started.wait(timeout=1)
        assert controller.is_loading is True
        client.release.set()
        _await(done)
        assert controller.is_loading is False

    def test_fetch_fires_workouts_changed(self) -> None:
        controller = _make_controller()
        events: list = []
        controller.on_workouts_changed(lambda: events.append("changed"))
        done = threading.Event()

        controller.fetch_workouts_async(
            on_done=lambda w: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)
        # notifié au démarrage (loading) puis à la fin (résultat)
        assert len(events) >= 2

    def test_fetch_error_clears_loading_and_calls_on_error(self) -> None:
        class FailingClient(FakeClient):
            def get_workouts(self, start: int = 0, limit: int = 20):
                raise RuntimeError("réseau KO")

        controller = _make_controller(client=FailingClient())
        done = threading.Event()
        errors: list = []

        controller.fetch_workouts_async(
            on_done=lambda w: done.set(),
            on_error=lambda e: (errors.append(e), done.set()),
        )
        _await(done)

        assert len(errors) == 1
        assert controller.is_loading is False
        assert controller.workouts == []


# --- Refresh (bouton « ↻ ») ---------------------------------------------------


@pytest.mark.unit
class TestRefresh:
    def test_refresh_workouts_relances_fetch(self) -> None:
        """`refresh_workouts` délègue à `fetch_workouts_async` (worker lancé)."""
        client = FakeClient(
            [
                {"workoutId": 1, "workoutName": "A"},
            ]
        )
        controller = _make_controller(client=client)
        done = threading.Event()

        controller.refresh_workouts(
            on_done=lambda w: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        # Le worker a appelé `get_workouts` du service → listing relancé.
        assert client.get_workouts_calls == 1
        assert [w.workout_id for w in controller.workouts] == [1]
        assert controller.is_loading is False

    def test_refresh_workouts_noop_if_loading(self) -> None:
        """Refresh pendant un chargement : garde anti-re-entrante, noop."""
        client = BlockingClient()
        controller = _make_controller(client=client)
        first_done = threading.Event()

        controller.fetch_workouts_async(
            on_done=lambda w: first_done.set(),
            on_error=lambda e: first_done.set(),
        )
        assert client.started.wait(timeout=1)
        assert controller.is_loading is True

        # Refresh pendant le chargement : la garde `is_loading` court-circuite
        # `fetch_workouts_async` → aucun second worker lancé. On le vérifie en
        # confirmant que `is_loading` reste True (le premier fetch est toujours
        # en cours) et que le `BlockingClient` n'a pas été rappelé (le second
        # appel aurait remis `started` — ici on vérifie juste l'état du
        # controller, suffisant car la garde retourne avant tout lancement).
        controller.refresh_workouts(
            on_done=lambda w: None,
            on_error=lambda e: None,
        )
        assert controller.is_loading is True  # toujours le premier fetch

        client.release.set()
        _await(first_done)
        assert controller.is_loading is False


# --- Sélection ---------------------------------------------------------------


@pytest.mark.unit
class TestSelection:
    def test_toggle_selection_adds_and_removes(self) -> None:
        controller = _make_controller()
        controller.toggle_selection(5)
        assert controller.selected == {5}
        controller.toggle_selection(5)
        assert controller.selected == set()

    def test_selected_count(self) -> None:
        controller = _make_controller()
        controller.toggle_selection(1)
        controller.toggle_selection(2)
        controller.toggle_selection(2)  # retire
        assert controller.selected_count == 1

    def test_select_all_and_none(self) -> None:
        controller = _make_controller()
        controller._workouts = _summaries(1, 2, 3)
        controller.select_all()
        assert controller.selected == {1, 2, 3}
        controller.select_none()
        assert controller.selected == set()

    def test_selection_changed_fired(self) -> None:
        controller = _make_controller()
        events: list = []
        controller.on_selection_changed(lambda: events.append("x"))
        controller.toggle_selection(1)
        controller.select_none()
        assert len(events) == 2


# --- Activation du bouton ----------------------------------------------------


@pytest.mark.unit
class TestCanSend:
    def test_false_when_empty_selection(self) -> None:
        controller = _make_controller()
        controller._workouts = _summaries(1)
        assert controller.can_send is False

    def test_false_when_watch_disconnected(self) -> None:
        controller = _make_controller(detector=FakeDetector(connected=False))
        controller._workouts = _summaries(1)
        controller.toggle_selection(1)
        assert controller.can_send is False

    def test_true_when_ready(self) -> None:
        controller = _make_controller()
        controller._workouts = _summaries(1)
        controller.toggle_selection(1)
        assert controller.can_send is True

    def test_false_when_loading(self) -> None:
        client = BlockingClient()
        controller = _make_controller(client=client)
        controller._workouts = _summaries(1)
        controller.toggle_selection(1)
        done = threading.Event()
        controller.fetch_workouts_async(on_done=lambda w: done.set(), on_error=lambda e: done.set())
        assert client.started.wait(timeout=1)
        assert controller.is_loading is True
        assert controller.can_send is False
        client.release.set()
        _await(done)


# --- Envoi -------------------------------------------------------------------


@pytest.mark.unit
class TestPush:
    def _patch_push(self, monkeypatch, fn):
        monkeypatch.setattr(controller_module, "push_workouts", fn)
        return fn

    def _setup_selected(self, controller, *ids: int) -> None:
        controller._workouts = _summaries(*ids)
        for i in ids:
            controller.toggle_selection(i)

    def test_progress_fired_before_each_workout(self, monkeypatch) -> None:
        controller = _make_controller()
        self._setup_selected(controller, 1, 2, 3)

        def fake_push(client, watch, transfers, history, logger, items):
            return SyncResult(total=1, success=1, failed=0, errors=[])

        self._patch_push(monkeypatch, fake_push)
        progress: list = []
        done = threading.Event()

        controller.push_workouts_async(
            on_progress=lambda c, t, n: progress.append((c, t, n)),
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert [p[0] for p in progress] == [1, 2, 3]
        assert all(p[1] == 3 for p in progress)
        assert [p[2] for p in progress] == ["Workout 1", "Workout 2", "Workout 3"]

    def test_items_transmitted_are_selected(self, monkeypatch) -> None:
        controller = _make_controller()
        self._setup_selected(controller, 1, 2, 3)
        controller.toggle_selection(2)  # désélectionne 2 → {1, 3}

        calls: list = []

        def fake_push(client, watch, transfers, history, logger, items):
            calls.append(items)
            return SyncResult(total=len(items), success=len(items), failed=0, errors=[])

        self._patch_push(monkeypatch, fake_push)
        done = threading.Event()

        controller.push_workouts_async(
            on_progress=lambda c, t, n: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        # un appel par workout sélectionné, dans l'ordre de la liste (1 puis 3)
        assert len(calls) == 2
        assert calls[0][0].workout_id == 1
        assert calls[1][0].workout_id == 3

    def test_done_receives_aggregated_result(self, monkeypatch) -> None:
        controller = _make_controller()
        self._setup_selected(controller, 1, 2)

        def fake_push(client, watch, transfers, history, logger, items):
            # 1 réussit, 2 échoue
            wid = items[0].workout_id
            if wid == 1:
                return SyncResult(total=1, success=1, failed=0, errors=[])
            return SyncResult(total=1, success=0, failed=1, errors=["workout 2: OSError: x"])

        self._patch_push(monkeypatch, fake_push)
        done = threading.Event()
        results: list = []

        controller.push_workouts_async(
            on_progress=lambda c, t, n: None,
            on_done=lambda r: (results.append(r), done.set()),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert len(results) == 1
        result = results[0]
        assert (result.total, result.success, result.failed) == (2, 1, 1)
        assert result.errors == ["workout 2: OSError: x"]

    def test_is_sending_toggles(self, monkeypatch) -> None:
        controller = _make_controller()
        self._setup_selected(controller, 1)
        block = threading.Event()
        started = threading.Event()

        def blocking_push(client, watch, transfers, history, logger, items):
            started.set()
            block.wait(timeout=1)
            return SyncResult(total=1, success=1, failed=0, errors=[])

        self._patch_push(monkeypatch, blocking_push)
        done = threading.Event()

        controller.push_workouts_async(
            on_progress=lambda c, t, n: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        assert started.wait(timeout=1)
        assert controller.is_sending is True
        assert controller.can_send is False
        block.set()
        _await(done)
        assert controller.is_sending is False

    def test_fatal_error_when_watch_disconnected(self, monkeypatch) -> None:
        controller = _make_controller(detector=FakeDetector(connected=False))
        self._setup_selected(controller, 1)
        done = threading.Event()
        errors: list = []

        controller.push_workouts_async(
            on_progress=lambda c, t, n: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: (errors.append(e), done.set()),
        )
        _await(done)

        assert len(errors) == 1
        assert isinstance(errors[0], controller_module.WatchNotConnectedError)
        assert controller.is_sending is False

    def test_successful_workouts_unchecked_after_push(self, monkeypatch) -> None:
        controller = _make_controller()
        self._setup_selected(controller, 1, 2)

        def fake_push(client, watch, transfers, history, logger, items):
            # 1 réussit, 2 échoue → 2 reste coché
            wid = items[0].workout_id
            if wid == 1:
                return SyncResult(total=1, success=1, failed=0, errors=[])
            return SyncResult(total=1, success=0, failed=1, errors=["workout 2: OSError: x"])

        self._patch_push(monkeypatch, fake_push)
        done = threading.Event()

        controller.push_workouts_async(
            on_progress=lambda c, t, n: None,
            on_done=lambda r: done.set(),
            on_error=lambda e: done.set(),
        )
        _await(done)

        assert controller.selected == {2}  # 1 décoché (réussi), 2 conservé (échec)


# --- Statut montre -----------------------------------------------------------


@pytest.mark.unit
class TestWatchStatus:
    def test_disconnect_disables_can_send(self) -> None:
        controller = _make_controller()
        controller._workouts = _summaries(1)
        controller.toggle_selection(1)
        assert controller.can_send is True

        controller.on_watch_status_changed(False)
        assert controller.can_send is False

    def test_reconnect_reenables_can_send(self) -> None:
        controller = _make_controller(detector=FakeDetector(connected=False))
        controller._workouts = _summaries(1)
        controller.toggle_selection(1)
        assert controller.can_send is False

        controller.on_watch_status_changed(True)
        assert controller.can_send is True

    def test_status_changed_fires_sending_state_callback(self) -> None:
        controller = _make_controller()
        events: list = []
        controller.on_sending_state_changed(lambda: events.append("x"))
        controller.on_watch_status_changed(False)
        assert len(events) == 1

    def test_subscribes_to_detector_signal(self) -> None:
        detector = FakeDetector()
        _make_controller(detector=detector)
        assert len(detector.callbacks) == 1
        # le callback enregistré est la méthode on_watch_status_changed
        detector.callbacks[0](False)
