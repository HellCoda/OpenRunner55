"""Tests unitaires du wrapper GarminClient (garminconnect mocké — zéro réseau).

Voir docs/decisions/adr-007.md (délai 3s, backoff 429, cascade 401) et adr-008.md.
"""

from __future__ import annotations

import pytest

from openrunner55.auth.authenticator import SessionNotFoundError
from openrunner55.garmin.client import GarminAuthError, GarminClient
from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)


class FakeGarmin:
    """Doublure de Garmin() avec des méthodes API pilotables."""

    def __init__(self):
        self.workouts_result: list[dict] = []
        self.activities_result = []
        self.workouts_errors: list[Exception] = []
        self.activities_errors: list[Exception] = []
        self.download_result: bytes = b""
        self.download_errors: list[Exception] = []
        self.downloaded_ids: list[int] = []
        self.calls: dict[str, int] = {
            "get_workouts": 0,
            "get_activities": 0,
            "download_workout": 0,
        }

    def get_workouts(self, start: int = 0, limit: int = 20) -> list[dict]:
        self.calls["get_workouts"] += 1
        if self.workouts_errors:
            raise self.workouts_errors.pop(0)
        return self.workouts_result

    def get_activities(self, start: int = 0, limit: int = 20):
        self.calls["get_activities"] += 1
        if self.activities_errors:
            raise self.activities_errors.pop(0)
        return self.activities_result

    def download_workout(self, workout_id: int) -> bytes:
        self.calls["download_workout"] += 1
        self.downloaded_ids.append(workout_id)
        if self.download_errors:
            raise self.download_errors.pop(0)
        return self.download_result


class FakeAuthenticator:
    """Doublure d'Authenticator : contrôle get_client() pour la cascade 401."""

    def __init__(self):
        self.clients: list[object] = []
        self.fail_next_get_client = False

    def get_client(self):
        if self.fail_next_get_client:
            raise SessionNotFoundError("pas de session")
        return self.clients.pop(0) if self.clients else None


@pytest.fixture
def fake_sleep(monkeypatch):
    """Ne dort jamais réellement, mais enregistre les délais demandés."""
    sleeps: list[float] = []

    def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("openrunner55.garmin.client.time.sleep", no_sleep)
    return sleeps


@pytest.fixture
def fake_monotonic(monkeypatch):
    """Horloge monotone pilotable : pour simuler l'écoulement du temps."""
    import openrunner55.garmin.client as client_mod

    state = {"now": 0.0}

    def now() -> float:
        return state["now"]

    monkeypatch.setattr(client_mod.time, "monotonic", now)
    return state


@pytest.mark.unit
class TestGarminClientBasic:
    def test_init_without_garmin_uses_authenticator(self) -> None:
        fake_auth = FakeAuthenticator()
        fake_garmin = FakeGarmin()
        fake_auth.clients.append(fake_garmin)
        client = GarminClient(authenticator=fake_auth)
        assert client._garmin is fake_garmin

    def test_get_workouts_returns_data(self) -> None:
        fake_auth = FakeAuthenticator()
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_result = [{"id": 1, "name": "Course 5k"}]
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        assert client.get_workouts() == [{"id": 1, "name": "Course 5k"}]

    def test_get_activities_returns_data(self) -> None:
        fake_auth = FakeAuthenticator()
        fake_garmin = FakeGarmin()
        fake_garmin.activities_result = [{"activityId": 42}]
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        assert client.get_activities() == [{"activityId": 42}]

    def test_forwards_arguments(self) -> None:
        fake_auth = FakeAuthenticator()
        fake_garmin = FakeGarmin()
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        client.get_workouts(start=5, limit=10)
        # le fake ignore les args mais la méthode est bien appelée
        assert fake_garmin.calls["get_workouts"] == 1


@pytest.mark.unit
class TestInterRequestDelay:
    def test_first_call_does_not_wait(self, fake_sleep) -> None:
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=FakeGarmin())
        client.get_workouts()
        assert fake_sleep == []

    def test_second_call_within_delay_waits(self, fake_sleep, fake_monotonic) -> None:
        fake_monotonic["now"] = 0.0
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=FakeGarmin())
        client.get_workouts()  # t=0
        fake_monotonic["now"] = 1.0  # 1s plus tard : il reste 2s à attendre
        client.get_activities()
        assert fake_sleep == [2.0]

    def test_second_call_after_delay_does_not_wait(self, fake_sleep, fake_monotonic) -> None:
        fake_monotonic["now"] = 0.0
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=FakeGarmin())
        client.get_workouts()
        fake_monotonic["now"] = 5.0  # 5s plus tard : délai déjà écoulé
        client.get_activities()
        assert fake_sleep == []


@pytest.mark.unit
class TestRetryOn429:
    def test_single_429_then_success(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_errors = [GarminConnectTooManyRequestsError("429")]
        fake_garmin.workouts_result = [{"id": 1}]
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        assert client.get_workouts() == [{"id": 1}]
        assert fake_garmin.calls["get_workouts"] == 2
        assert fake_sleep == [1.0]  # backoff 1s au premier retry

    def test_exponential_backoff_sequence(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_errors = [
            GarminConnectTooManyRequestsError("429"),
            GarminConnectTooManyRequestsError("429"),
        ]
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        client.get_workouts()
        assert fake_sleep == [1.0, 2.0]  # 1s puis 2s

    def test_max_retries_then_raises(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_errors = [
            GarminConnectTooManyRequestsError("429"),
            GarminConnectTooManyRequestsError("429"),
            GarminConnectTooManyRequestsError("429"),
            GarminConnectTooManyRequestsError("429"),
        ]
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        with pytest.raises(GarminConnectTooManyRequestsError):
            client.get_workouts()
        # 1 appel initial + 3 retries = 4 tentatives
        assert fake_garmin.calls["get_workouts"] == 4
        assert fake_sleep == [1.0, 2.0, 4.0]


@pytest.mark.unit
class TestReLoginOn401:
    def test_401_triggers_relogin_and_retries(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_errors = [GarminConnectAuthenticationError("401")]
        fake_garmin.workouts_result = [{"id": 1}]
        fake_auth = FakeAuthenticator()
        fresh_garmin = FakeGarmin()
        fresh_garmin.workouts_result = [{"id": 2}]
        fake_auth.clients.append(fresh_garmin)
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        assert client.get_workouts() == [{"id": 2}]
        # l'appel a été rejoué sur le client frais
        assert fresh_garmin.calls["get_workouts"] == 1

    def test_401_without_fresh_client_raises_auth_error(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.workouts_errors = [GarminConnectAuthenticationError("401")]
        fake_auth = FakeAuthenticator()
        fake_auth.fail_next_get_client = True
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        with pytest.raises(GarminAuthError):
            client.get_workouts()

    def test_relogin_only_once(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        # Le client frais échoue aussi en 401 → pas de nouvelle cascade, erreur remontée
        fake_garmin.workouts_errors = [GarminConnectAuthenticationError("401")]
        fake_auth = FakeAuthenticator()
        fresh = FakeGarmin()
        fresh.workouts_errors = [GarminConnectAuthenticationError("401")]
        fake_auth.clients.append(fresh)
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        with pytest.raises(GarminConnectAuthenticationError):
            client.get_workouts()


@pytest.mark.unit
class TestDownloadWorkout:
    def test_returns_bytes(self) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.download_result = b"\x0e\x10\x0e\x00"  # en-tête FIT
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        assert client.download_workout(123) == b"\x0e\x10\x0e\x00"

    def test_forwards_workout_id(self) -> None:
        fake_garmin = FakeGarmin()
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        client.download_workout(42)
        assert fake_garmin.downloaded_ids == [42]

    def test_inherits_inter_request_delay(self, fake_sleep, fake_monotonic) -> None:
        fake_monotonic["now"] = 0.0
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=FakeGarmin())
        client.get_workouts()  # t=0
        fake_monotonic["now"] = 1.0  # 1s plus tard : il reste 2s
        client.download_workout(1)
        assert fake_sleep == [2.0]

    def test_retries_on_429(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.download_errors = [GarminConnectTooManyRequestsError("429")]
        fake_garmin.download_result = b"\x0e\x10"
        client = GarminClient(authenticator=FakeAuthenticator(), garmin=fake_garmin)
        assert client.download_workout(1) == b"\x0e\x10"
        assert fake_garmin.calls["download_workout"] == 2
        assert fake_sleep == [1.0]  # backoff 1s au premier retry

    def test_relogs_in_on_401(self, fake_sleep) -> None:
        fake_garmin = FakeGarmin()
        fake_garmin.download_errors = [GarminConnectAuthenticationError("401")]
        fake_auth = FakeAuthenticator()
        fresh_garmin = FakeGarmin()
        fresh_garmin.download_result = b"\x0e\x10\x0e\x00"
        fake_auth.clients.append(fresh_garmin)
        client = GarminClient(authenticator=fake_auth, garmin=fake_garmin)
        assert client.download_workout(7) == b"\x0e\x10\x0e\x00"
        assert fresh_garmin.calls["download_workout"] == 1
        assert fresh_garmin.downloaded_ids == [7]
