"""Tests unitaires du service sync/workouts.py (mocks GarminClient + WatchFilesystem).

Voir docs/decisions/adr-002.md (flux Cloud → Montre) et adr-008.md (stratégie de test).

`fetch_workouts` et `push_workouts` sont testés avec des doublures : aucun appel
réseau ni montre branchée. Le slugify est testé exhaustivement.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from openrunner55.sync.workouts import (
    WorkoutSummary,
    fetch_workouts,
    push_workouts,
    slugify,
)


# --- Doublures ---------------------------------------------------------------


class FakeClient:
    """Doublure de GarminClient : get_workouts() pilotable, download pilotable."""

    def __init__(self, workouts: list[dict], downloads: dict[int, object]):
        self._workouts = workouts
        self._downloads = downloads
        self.get_workouts_calls = 0
        self.downloaded: list[int] = []

    def get_workouts(self, start: int = 0, limit: int = 20) -> list[dict]:
        self.get_workouts_calls += 1
        return self._workouts

    def download_workout(self, workout_id: int) -> bytes:
        self.downloaded.append(workout_id)
        result = self._downloads[workout_id]
        if isinstance(result, Exception):
            raise result
        return result


class FakeWatch:
    """Doublure de WatchFilesystem : list_fit_files et write_fit en mémoire."""

    def __init__(self, existing: list[Path] | None = None, write_error: Exception | None = None):
        self._existing = existing or []
        self.write_error = write_error
        self.written: list[tuple[Path, bytes]] = []

    def list_fit_files(self, category: str) -> list[Path]:
        return self._existing

    def write_fit(self, path: Path, data: bytes) -> None:
        if self.write_error is not None:
            raise self.write_error
        self.written.append((path, data))


class FakeTransfers:
    def __init__(self):
        self.marked: list[tuple[str, str, str]] = []

    def mark_transferred(self, file_name, direction, source, gc_activity_id=None) -> None:
        self.marked.append((file_name, direction, source))


class FakeHistory:
    def __init__(self):
        self.logs: list[tuple[str, int, str, str | None]] = []

    def log_sync(self, direction, file_count, status, details=None) -> None:
        self.logs.append((direction, file_count, status, details))


class FakeLogger:
    def __init__(self):
        self.logs: list[tuple[str, str, str]] = []

    def log(self, operation, status, message) -> None:
        self.logs.append((operation, status, message))


# --- Slugify ----------------------------------------------------------------


@pytest.mark.unit
class TestSlugify:
    def test_lowercase(self) -> None:
        assert slugify("Course 5k") == "course_5k"

    def test_accents_removed(self) -> None:
        assert slugify("Course à pied") == "course_a_pied"
        assert slugify("ÉCOLE") == "ecole"
        assert slugify("Piramyde") == "piramyde"

    def test_spaces_to_underscores(self) -> None:
        assert slugify("Run Long") == "run_long"
        assert slugify("Hello  World") == "hello_world"  # espaces consécutifs repliés

    def test_special_chars_removed(self) -> None:
        assert slugify("Test-workout-1") == "testworkout1"
        assert slugify("100% effort") == "100_effort"

    def test_underscore_preserved(self) -> None:
        assert slugify("10K_...M") == "10k_m"

    def test_digits_preserved(self) -> None:
        assert slugify("10k12KM") == "10k12km"

    def test_max_length_40(self) -> None:
        assert slugify("a" * 60) == "a" * 40
        assert len(slugify("b" * 100)) == 40

    def test_empty_result_falls_back_to_workout(self) -> None:
        assert slugify("") == "workout"
        assert slugify("!!!") == "workout"
        assert slugify("   ") == "workout"

    def test_leading_trailing_underscores_stripped(self) -> None:
        assert slugify("  Hello  ") == "hello"
        assert slugify("-foo-") == "foo"

    def test_parentheses_and_mixed(self) -> None:
        assert slugify("Course à pied (10 km)") == "course_a_pied_10_km"


# --- fetch_workouts ----------------------------------------------------------


def _workout(wid, name, updated=None, created=None, sport="running") -> dict:
    data: dict = {"workoutId": wid, "workoutName": name, "sportType": {"sportTypeKey": sport}}
    if updated:
        data["updatedDate"] = updated
    if created:
        data["createdDate"] = created
    return data


@pytest.mark.unit
class TestFetchWorkouts:
    def test_extracts_metadata(self) -> None:
        client = FakeClient(
            [{"workoutId": 1, "workoutName": "Interval", "updatedDate": "2026-08-01T10:00:00.0", "sportType": {"sportTypeKey": "running"}}],
            {},
        )
        result = fetch_workouts(client)
        assert result == [WorkoutSummary(1, "Interval", datetime(2026, 8, 1, 10, 0, 0), "running")]

    def test_sorts_most_recent_first(self) -> None:
        client = FakeClient(
            [
                _workout(1, "old", updated="2026-01-01T00:00:00.0"),
                _workout(2, "new", updated="2026-08-01T00:00:00.0"),
                _workout(3, "mid", updated="2026-04-01T00:00:00.0"),
            ],
            {},
        )
        ids = [w.workout_id for w in fetch_workouts(client)]
        assert ids == [2, 3, 1]

    def test_missing_date_sinks_to_end_keeping_order(self) -> None:
        client = FakeClient(
            [
                _workout(1, "dated", updated="2026-01-01T00:00:00.0"),
                _workout(2, "nodate-a"),
                _workout(3, "nodate-b"),
            ],
            {},
        )
        ids = [w.workout_id for w in fetch_workouts(client)]
        assert ids == [1, 2, 3]  # 1 daté d'abord, puis 2 et 3 dans l'ordre API

    def test_updated_date_preferred_over_created(self) -> None:
        client = FakeClient(
            [
                _workout(1, "w", updated="2026-08-01T00:00:00.0", created="2026-01-01T00:00:00.0"),
            ],
            {},
        )
        assert fetch_workouts(client)[0].date == datetime(2026, 8, 1)

    def test_type_defaults_to_unknown(self) -> None:
        client = FakeClient([{"workoutId": 1, "workoutName": "x"}], {})
        assert fetch_workouts(client)[0].type == "unknown"


# --- push_workouts -----------------------------------------------------------


def _summary(wid: int, name: str = "Foo") -> WorkoutSummary:
    return WorkoutSummary(workout_id=wid, name=name, date=None, type="running")


@pytest.mark.unit
class TestPushWorkouts:
    def _push(self, client, watch, transfers, history, logger, items):
        return push_workouts(client, watch, transfers, history, logger, items)

    def test_happy_path(self) -> None:
        client = FakeClient([], {1: b"FIT-bytes"})
        watch = FakeWatch()
        transfers = FakeTransfers()
        history = FakeHistory()
        logger = FakeLogger()

        result = self._push(client, watch, transfers, history, logger, [_summary(1, "Interval Run")])

        assert result.total == 1
        assert result.success == 1
        assert result.failed == 0
        assert result.errors == []
        assert watch.written == [(Path("Workouts/interval_run.FIT"), b"FIT-bytes")]
        assert transfers.marked == [("interval_run.FIT", "down", "workout")]
        assert history.logs[0][:3] == ("down", 1, "success")

    def test_collision_suffix(self) -> None:
        client = FakeClient([], {1: b"x"})
        watch = FakeWatch(existing=[Path("Workouts/foo.FIT")])
        self._push(client, watch, FakeTransfers(), FakeHistory(), FakeLogger(), [_summary(1, "Foo")])
        assert watch.written == [(Path("Workouts/foo_2.FIT"), b"x")]

    def test_collision_suffix_increments(self) -> None:
        # foo.FIT et foo_2.FIT existent déjà → foo_3.FIT
        client = FakeClient([], {1: b"x"})
        watch = FakeWatch(existing=[Path("Workouts/foo.FIT"), Path("Workouts/foo_2.FIT")])
        self._push(client, watch, FakeTransfers(), FakeHistory(), FakeLogger(), [_summary(1, "Foo")])
        assert watch.written == [(Path("Workouts/foo_3.FIT"), b"x")]

    def test_collision_suffix_is_case_insensitive(self) -> None:
        # FAT32 : "FOO.FIT" existant → "foo" est en collision.
        client = FakeClient([], {1: b"x"})
        watch = FakeWatch(existing=[Path("Workouts/FOO.FIT")])
        self._push(client, watch, FakeTransfers(), FakeHistory(), FakeLogger(), [_summary(1, "Foo")])
        assert watch.written == [(Path("Workouts/foo_2.FIT"), b"x")]

    def test_failure_continues_and_records(self) -> None:
        client = FakeClient([], {1: b"ok", 2: OSError("déconnexion USB")})
        watch = FakeWatch()
        transfers = FakeTransfers()
        history = FakeHistory()
        logger = FakeLogger()

        result = self._push(
            client, watch, transfers, history, logger,
            [_summary(1, "Ok"), _summary(2, "Ko")],
        )

        assert result.total == 2
        assert result.success == 1
        assert result.failed == 1
        assert len(result.errors) == 1
        assert "workout 2" in result.errors[0]
        assert "OSError" in result.errors[0]
        # seul le workout 1 a été écrit
        assert [p.name for p, _ in watch.written] == ["ok.FIT"]
        # statut partiel
        assert history.logs[0][2] == "partial"

    def test_write_fit_failure_records(self) -> None:
        # Échec au niveau de l'écriture USB (pas du download).
        client = FakeClient([], {1: b"ok"})
        watch = FakeWatch(write_error=OSError("déconnexion USB"))
        history = FakeHistory()

        result = self._push(client, watch, FakeTransfers(), history, FakeLogger(), [_summary(1)])

        assert result.failed == 1
        assert result.success == 0
        assert watch.written == []
        assert "OSError" in result.errors[0]
        assert history.logs[0][2] == "failed"

    def test_all_failed_status(self) -> None:
        client = FakeClient([], {1: OSError("x")})
        watch = FakeWatch()
        history = FakeHistory()
        result = self._push(client, watch, FakeTransfers(), history, FakeLogger(), [_summary(1, "A")])
        assert result.failed == 1
        assert result.success == 0
        assert history.logs[0][2] == "failed"

    def test_empty_items_noop(self) -> None:
        client = FakeClient([], {})
        watch = FakeWatch()
        history = FakeHistory()
        result = self._push(client, watch, FakeTransfers(), history, FakeLogger(), [])
        assert result.total == 0
        assert result.success == 0
        assert history.logs == []  # aucune sync loggée
        assert client.downloaded == []  # aucun download

    def test_duplicate_names_in_batch_get_suffix(self) -> None:
        # Deux workouts au même nom dans le même batch → pas d'écrasement.
        client = FakeClient([], {1: b"one", 2: b"two"})
        watch = FakeWatch()
        transfers = FakeTransfers()
        self._push(client, watch, transfers, FakeHistory(), FakeLogger(), [_summary(1, "Same"), _summary(2, "Same")])
        names = [p.name for p, _ in watch.written]
        assert names == ["same.FIT", "same_2.FIT"]

    def test_missing_name_uses_workout_id(self) -> None:
        client = FakeClient([], {7: b"x"})
        watch = FakeWatch()
        self._push(client, watch, FakeTransfers(), FakeHistory(), FakeLogger(), [_summary(7, "")])
        assert [p.name for p, _ in watch.written] == ["workout_7.FIT"]

    def test_details_are_redacted(self) -> None:
        # Retour 2 : un message d'erreur portant un email/token est masqué dans
        # sync_history.details (cohérent avec operation_logs).
        client = FakeClient([], {1: OSError("user@example.com password=secret")})
        watch = FakeWatch()
        history = FakeHistory()
        self._push(client, watch, FakeTransfers(), history, FakeLogger(), [_summary(1)])
        details = history.logs[0][3]
        assert "user@example.com" not in details
        assert "secret" not in details
        assert "[REDACTED]" in details
