"""Tests unitaires du service sync/activities.py (mocks WatchFilesystem + stores).

Voir docs/decisions/adr-002.md (flux Montre → GC) et adr-008.md (stratégie de test).

`list_uploadable_files` (et `push_activities` à l'étape suivante) sont testés
avec des doublures : aucune montre réelle, aucun appel réseau.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from garminconnect import GarminConnectConnectionError

from openrunner55.sync.activities import (
    UPLOADABLE_CATEGORIES,
    UploadableFile,
    list_uploadable_files,
    push_activities,
)


# --- Doublures ---------------------------------------------------------------


class FakeWatch:
    """Doublure de WatchFilesystem : list_fit_files et file_size pilotables."""

    def __init__(
        self,
        files: dict[str, list[Path]] | None = None,
        sizes: dict[Path, int] | None = None,
    ):
        self._files = files or {}
        self._sizes = sizes or {}
        self.queried_categories: list[str] = []

    def list_fit_files(self, category: str) -> list[Path]:
        self.queried_categories.append(category)
        return self._files.get(category, [])

    def file_size(self, path: Path) -> int:
        return self._sizes.get(path, 0)

    def absolute_path(self, path: Path) -> Path:
        return Path("/fake/GARMIN") / path


class FakeTransfers:
    """Doublure de TransferredFilesStore : dédup `(file_name, source)` en mémoire."""

    def __init__(self, transferred: set[tuple[str, str]] | None = None):
        self._transferred = transferred or set()
        self.queried: list[tuple[str, str, str | None]] = []
        self.marked: list[tuple[str, str, str, int | None]] = []

    def is_transferred(self, file_name: str, direction: str, source: str | None = None) -> bool:
        self.queried.append((file_name, direction, source))
        return (file_name, source) in self._transferred

    def mark_transferred(
        self,
        file_name: str,
        direction: str,
        source: str,
        gc_activity_id: int | None = None,
    ) -> None:
        self.marked.append((file_name, direction, source, gc_activity_id))


class FakeClient:
    """Doublure de GarminClient : upload_activity pilotable par basename."""

    def __init__(self, results: dict[str, object] | None = None):
        self._results = results or {}
        self.uploaded: list[str] = []

    def upload_activity(self, file_path: str | Path) -> dict:
        self.uploaded.append(str(file_path))
        result = self._results.get(Path(file_path).name)
        if isinstance(result, Exception):
            raise result
        return result if result is not None else {"detailedImportResult": {"successes": [1]}}


class FakeHistory:
    def __init__(self):
        self.logs: list[tuple[str, int, str, str | None]] = []

    def log_sync(self, direction: str, file_count: int, status: str, details: str | None = None) -> None:
        self.logs.append((direction, file_count, status, details))


class FakeLogger:
    def __init__(self):
        self.logs: list[tuple[str, str, str]] = []

    def log(self, operation: str, status: str, message: str) -> None:
        self.logs.append((operation, status, message))


# --- list_uploadable_files ---------------------------------------------------


@pytest.mark.unit
class TestListUploadableFiles:
    def test_empty_watch_returns_empty_list(self) -> None:
        assert list_uploadable_files(FakeWatch(), FakeTransfers()) == []

    def test_lists_all_four_categories_in_order(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/2026-08-07-08-29-33.fit")],
                "Monitor": [Path("Monitor/M85K3715.FIT")],
                "Sleep": [Path("Sleep/S7O00000.FIT")],
                "Metrics": [Path("Metrics/G8400529.fit")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())

        assert [f.path for f in result] == [
            Path("Activity/2026-08-07-08-29-33.fit"),
            Path("Monitor/M85K3715.FIT"),
            Path("Sleep/S7O00000.FIT"),
            Path("Metrics/G8400529.fit"),
        ]
        # category portée en minuscules (convention brief), ordre UPLOADABLE_CATEGORIES
        assert [f.category for f in result] == ["activity", "monitor", "sleep", "metrics"]

    def test_excludes_summary(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/a.fit")],
                "SUMMARY": [Path("SUMMARY/abc.FIT")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())

        assert [f.path for f in result] == [Path("Activity/a.fit")]
        # SUMMARY n'est jamais interrogé (pas dans UPLOADABLE_CATEGORIES)
        assert "SUMMARY" not in watch.queried_categories
        assert watch.queried_categories == list(UPLOADABLE_CATEGORIES)

    def test_marks_already_transferred(self) -> None:
        watch = FakeWatch(
            files={
                "Activity": [Path("Activity/a.fit"), Path("Activity/b.fit")],
            }
        )
        transfers = FakeTransfers(transferred={("a.fit", "activity")})
        result = list_uploadable_files(watch, transfers)

        by_name = {f.path.name: f for f in result}
        assert by_name["a.fit"].already_transferred is True
        assert by_name["b.fit"].already_transferred is False

    def test_dedup_uses_basename_and_lowercase_source(self) -> None:
        watch = FakeWatch(
            files={"Activity": [Path("Activity/2026-08-07-08-29-33.fit")]}
        )
        transfers = FakeTransfers()
        list_uploadable_files(watch, transfers)

        # D1 : file_name = basename (path.name), source = catégorie minuscule
        assert transfers.queried == [
            ("2026-08-07-08-29-33.fit", "up", "activity")
        ]

    def test_records_file_size(self) -> None:
        watch = FakeWatch(
            files={"Activity": [Path("Activity/a.fit")]},
            sizes={Path("Activity/a.fit"): 1234},
        )
        result = list_uploadable_files(watch, FakeTransfers())
        assert result[0].size == 1234

    def test_name_order_preserved_within_category(self) -> None:
        # Le tri par nom est délégué à list_fit_files ; le service préserve
        # l'ordre retourné (chronologique pour Activity/).
        watch = FakeWatch(
            files={
                "Activity": [
                    Path("Activity/2026-08-01-08-00-00.fit"),
                    Path("Activity/2026-08-02-08-00-00.fit"),
                ],
                "Monitor": [Path("Monitor/b.FIT"), Path("Monitor/a.FIT")],
            }
        )
        result = list_uploadable_files(watch, FakeTransfers())
        assert [f.path for f in result] == [
            Path("Activity/2026-08-01-08-00-00.fit"),
            Path("Activity/2026-08-02-08-00-00.fit"),
            Path("Monitor/b.FIT"),
            Path("Monitor/a.FIT"),
        ]


# --- push_activities ---------------------------------------------------------


def _item(
    path: str,
    category: str = "activity",
    size: int = 100,
    already: bool = False,
) -> UploadableFile:
    return UploadableFile(
        path=Path(path), category=category, size=size, already_transferred=already
    )


@pytest.mark.unit
class TestPushActivities:
    def test_happy_path(self) -> None:
        client = FakeClient()
        transfers = FakeTransfers()
        history = FakeHistory()
        logger = FakeLogger()

        result = push_activities(
            client, FakeWatch(), transfers, history, logger,
            [_item("Activity/a.fit", "activity")],
        )

        assert result.total == 1
        assert result.success == 1
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == []
        # chemin absolu résolu passé à upload_activity
        assert client.uploaded == ["/fake/GARMIN/Activity/a.fit"]
        # marqué avec basename + source (pas de gc_activity_id au MVP)
        assert transfers.marked == [("a.fit", "up", "activity", None)]
        assert history.logs[0][:3] == ("up", 1, "success")

    def test_source_derived_from_category(self) -> None:
        transfers = FakeTransfers()
        push_activities(
            FakeClient(), FakeWatch(), transfers, FakeHistory(), FakeLogger(),
            [_item("Monitor/M85K3715.FIT", category="monitor")],
        )
        assert transfers.marked == [("M85K3715.FIT", "up", "monitor", None)]

    def test_skips_already_transferred(self) -> None:
        client = FakeClient()
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), FakeHistory(), FakeLogger(),
            [_item("Activity/a.fit", already=True), _item("Activity/b.fit")],
        )

        assert result.skipped == 1
        assert result.success == 1
        assert result.failed == 0
        # seul b est uploadé (a est skippé sans appel API)
        assert client.uploaded == ["/fake/GARMIN/Activity/b.fit"]

    def test_failure_continues_and_collects(self) -> None:
        client = FakeClient(results={"b.fit": OSError("déconnexion USB")})
        transfers = FakeTransfers()
        history = FakeHistory()
        logger = FakeLogger()

        result = push_activities(
            client, FakeWatch(), transfers, history, logger,
            [_item("Activity/a.fit"), _item("Activity/b.fit"), _item("Activity/c.fit")],
        )

        assert result.total == 3
        assert result.success == 2
        assert result.failed == 1
        assert len(result.errors) == 1
        assert "file Activity/b.fit" in result.errors[0]
        assert "OSError" in result.errors[0]
        # a et c marqués, b non
        assert [m[0] for m in transfers.marked] == ["a.fit", "c.fit"]
        assert history.logs[0][2] == "partial"
        # logger.log appelé pour l'échec
        assert any(
            status == "error" and "b.fit" in message
            for _, status, message in logger.logs
        )

    def test_all_failed_status(self) -> None:
        client = FakeClient(results={"a.fit": OSError("x")})
        history = FakeHistory()
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), history, FakeLogger(),
            [_item("Activity/a.fit")],
        )
        assert result.failed == 1
        assert result.success == 0
        assert history.logs[0][2] == "failed"

    def test_empty_items_noop(self) -> None:
        history = FakeHistory()
        client = FakeClient()
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), history, FakeLogger(), []
        )
        assert result.total == 0
        assert result.success == 0
        assert result.failed == 0
        assert result.skipped == 0
        assert result.errors == []
        assert history.logs == []  # aucune sync loggée
        assert client.uploaded == []  # aucun upload

    def test_all_skipped_status_success(self) -> None:
        history = FakeHistory()
        result = push_activities(
            FakeClient(), FakeWatch(), FakeTransfers(), history, FakeLogger(),
            [_item("Activity/a.fit", already=True), _item("Activity/b.fit", already=True)],
        )
        assert result.skipped == 2
        assert result.success == 0
        assert result.failed == 0
        # D5 : tout skippé → succès, file_count = 0 (aucun échec)
        assert history.logs[0][:3] == ("up", 0, "success")

    def test_log_sync_file_count_is_uploaded_count(self) -> None:
        history = FakeHistory()
        push_activities(
            FakeClient(), FakeWatch(), FakeTransfers(), history, FakeLogger(),
            [
                _item("Activity/a.fit", already=True),
                _item("Activity/b.fit"),
                _item("Activity/c.fit"),
            ],
        )
        # file_count = fichiers réellement uploadés (2), pas total (3)
        assert history.logs[0][1] == 2

    def test_details_are_redacted(self) -> None:
        # Un message d'erreur portant un email/token est masqué dans
        # sync_history.details (cohérent avec operation_logs).
        client = FakeClient(results={"a.fit": OSError("user@example.com password=secret")})
        history = FakeHistory()
        push_activities(
            client, FakeWatch(), FakeTransfers(), history, FakeLogger(),
            [_item("Activity/a.fit")],
        )
        details = history.logs[0][3]
        assert "user@example.com" not in details
        assert "secret" not in details
        assert "[REDACTED]" in details

    # --- 409 Duplicate Activity → skip (Epic 5, chantier 1) -------------------

    def test_409_treated_as_skip(self) -> None:
        # La lib garminconnect lève GarminConnectConnectionError("API Error 409 - ...")
        # sur un 409 Duplicate Activity (cf. note module sync/activities.py).
        client = FakeClient(
            results={"a.fit": GarminConnectConnectionError("API Error 409 - duplicate")}
        )
        transfers = FakeTransfers()
        history = FakeHistory()
        logger = FakeLogger()

        result = push_activities(
            client, FakeWatch(), transfers, history, logger,
            [_item("Activity/a.fit")],
        )

        assert result.skipped == 1
        assert result.failed == 0
        assert result.success == 0
        assert result.errors == []
        # GC a confirmé la présence → on marque le fichier comme transféré.
        assert transfers.marked == [("a.fit", "up", "activity", None)]
        # Log info (pas d'erreur) mentionnant le fichier.
        assert any(
            status == "info" and "a.fit" in message
            for _, status, message in logger.logs
        )
        assert not any(
            status == "error" for _, status, _ in logger.logs
        )

    def test_409_mixed_with_success(self) -> None:
        client = FakeClient(
            results={"a.fit": GarminConnectConnectionError("API Error 409 - duplicate")}
        )
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), FakeHistory(), FakeLogger(),
            [_item("Activity/a.fit"), _item("Activity/b.fit")],
        )

        assert result.skipped == 1
        assert result.success == 1
        assert result.failed == 0
        assert result.errors == []

    def test_409_mixed_with_real_failure(self) -> None:
        client = FakeClient(
            results={
                "a.fit": GarminConnectConnectionError("API Error 409 - duplicate"),
                "b.fit": OSError("déconnexion USB"),
            }
        )
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), FakeHistory(), FakeLogger(),
            [_item("Activity/a.fit"), _item("Activity/b.fit")],
        )

        assert result.skipped == 1
        assert result.failed == 1
        assert result.success == 0
        assert len(result.errors) == 1
        assert "b.fit" in result.errors[0]

    def test_non_409_connection_error_still_failed(self) -> None:
        # Garde-fou : une GarminConnectConnectionError dont le message ne
        # contient ni "409" ni "duplicate" reste un échec (pas de skip).
        client = FakeClient(
            results={"a.fit": GarminConnectConnectionError("API Error 503 - unavailable")}
        )
        result = push_activities(
            client, FakeWatch(), FakeTransfers(), FakeHistory(), FakeLogger(),
            [_item("Activity/a.fit")],
        )

        assert result.failed == 1
        assert result.skipped == 0
        assert result.success == 0
        assert len(result.errors) == 1
