"""Tests unitaires du WatchDetector (watch Core) — pyudev mocké, zéro matériel.

Voir docs/decisions/adr-006.md (détection USB) et adr-008.md (stratégie de test).

Le détecteur est testé :
- via `tmp_path` pour simuler l'arborescence du volume (création/suppression du
  fichier de confirmation `GARMIN/GARMIN/GarminDevice.xml`) ;
- avec `pyudev` neutralisé (fixture `no_pyudev`) pour forcer le repli polling ;
- avec l'émission de signal rendue synchrone (fixture `direct_emit`) pour
  pouvoir observer les callbacks sans boucle GTK.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from openrunner55.watch.detector import WatchDetector, VOLUME_LABEL


def _wait_until(predicate, timeout: float = 2.0) -> bool:
    """Attend que `predicate()` soit vrai, au plus `timeout` secondes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _confirmation_path(mount_root: Path) -> Path:
    """Chemin du fichier de confirmation FR55 sous un `mount_root` donné."""
    return mount_root / VOLUME_LABEL / "GARMIN" / "GarminDevice.xml"


def _mount_watch(mount_root: Path) -> Path:
    """Crée le fichier de confirmation (simule une FR55 branchée)."""
    path = _confirmation_path(mount_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"<Device>FR55</Device>")
    return path


@pytest.fixture
def direct_emit(monkeypatch):
    """Neutralise GLib : l'émission du signal devient synchrone (observable)."""
    monkeypatch.setattr("openrunner55.watch.detector._GLib", None)


@pytest.fixture
def no_pyudev(monkeypatch):
    """Simule l'absence de pyudev : le détecteur replie sur le polling seul."""
    monkeypatch.setattr("openrunner55.watch.detector._pyudev", None)


@pytest.fixture
def detector(tmp_path: Path) -> WatchDetector:
    """Détecteur pointant sur un `tmp_path` (aucune montre réelle)."""
    return WatchDetector(mount_root=tmp_path)


class FakeDevice:
    """Doublure d'un Device pyudev (expose `get(key, default)`)."""

    def __init__(self, props: dict[str, str]):
        self._props = props

    def get(self, key: str, default=None):
        return self._props.get(key, default)


@pytest.mark.unit
class TestState:
    def test_initial_state_disconnected(self, detector) -> None:
        assert detector.is_connected() is False
        assert detector.get_mount_path() is None

    def test_connected_after_confirmation_file_created(self, detector, tmp_path) -> None:
        _mount_watch(tmp_path)
        assert detector._check_state() is True
        assert detector.is_connected() is True

    def test_mount_path_returns_volume_when_connected(self, detector, tmp_path) -> None:
        _mount_watch(tmp_path)
        detector._check_state()
        assert detector.get_mount_path() == tmp_path / VOLUME_LABEL

    def test_disconnected_after_file_removed(self, detector, tmp_path) -> None:
        path = _mount_watch(tmp_path)
        detector._check_state()
        path.unlink()
        assert detector._check_state() is False
        assert detector.is_connected() is False
        assert detector.get_mount_path() is None

    def test_requires_garmin_device_xml(self, detector, tmp_path) -> None:
        # Volume monté mais sans fichier de confirmation → pas une FR55
        (tmp_path / VOLUME_LABEL / "GARMIN").mkdir(parents=True)
        assert detector._check_state() is False
        assert detector.is_connected() is False


@pytest.mark.unit
class TestSignal:
    def test_callback_fired_on_connect(self, detector, tmp_path, direct_emit) -> None:
        events: list[bool] = []
        detector.on_status_changed(events.append)
        _mount_watch(tmp_path)
        detector._check_state()
        assert events == [True]

    def test_callback_fired_on_disconnect(self, detector, tmp_path, direct_emit) -> None:
        events: list[bool] = []
        detector.on_status_changed(events.append)
        path = _mount_watch(tmp_path)
        detector._check_state()
        path.unlink()
        detector._check_state()
        assert events == [True, False]

    def test_no_callback_when_state_unchanged(self, detector, tmp_path, direct_emit) -> None:
        events: list[bool] = []
        detector.on_status_changed(events.append)
        detector._check_state()  # déconnecté → déconnecté : aucun signal
        detector._check_state()
        assert events == []

    def test_multiple_callbacks_all_fired(self, detector, tmp_path, direct_emit) -> None:
        events_a: list[bool] = []
        events_b: list[bool] = []
        detector.on_status_changed(events_a.append)
        detector.on_status_changed(events_b.append)
        _mount_watch(tmp_path)
        detector._check_state()
        assert events_a == [True]
        assert events_b == [True]


@pytest.mark.unit
class TestUdev:
    def test_is_garmin_device_matches_label(self) -> None:
        assert WatchDetector._is_garmin_device(FakeDevice({"ID_FS_LABEL": "GARMIN"})) is True

    def test_is_garmin_device_rejects_other_label(self) -> None:
        assert WatchDetector._is_garmin_device(FakeDevice({"ID_FS_LABEL": "DATA"})) is False

    def test_is_garmin_device_without_label(self) -> None:
        assert WatchDetector._is_garmin_device(FakeDevice({})) is False

    def test_start_monitor_falls_back_when_pyudev_missing(self, detector, no_pyudev) -> None:
        assert detector._start_monitor() is None


@pytest.mark.unit
class TestLifecycle:
    def test_start_stop_lifecycle(self, detector, no_pyudev, direct_emit) -> None:
        detector.start()
        try:
            assert detector._thread is not None
            assert detector._thread.is_alive()
        finally:
            detector.stop()
        assert detector._thread is None

    def test_polling_detects_mount_and_unmount(self, tmp_path, no_pyudev, direct_emit) -> None:
        detector = WatchDetector(mount_root=tmp_path, poll_interval=0.02)
        events: list[bool] = []
        detector.on_status_changed(events.append)
        detector.start()
        try:
            path = _mount_watch(tmp_path)
            assert _wait_until(lambda: events == [True])
            path.unlink()
            assert _wait_until(lambda: events == [True, False])
        finally:
            detector.stop()
