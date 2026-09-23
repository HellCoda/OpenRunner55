"""Tests unitaires du `HistoryController` (logique de présentation sans GTK).

Voir docs/decisions/adr-008.md (stratégie de test) et le brief
`docs/dev/Epic-4-brief.md` (contrat du controller).

Le controller est testé avec une doublure de `HistoryService` qui trace les
appels (`get_sync_history`, `get_operation_logs`) et retourne des listes
pilotables. Aucune boucle GTK, aucun store réel : le service délègue en
lecture seule, on vérifie ici l'état et les notifications.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from openrunner55.sync.history import LogRecord, SyncRecord
from openrunner55.ui.history_controller import HistoryController, SyncRecordDetail


# --- Doublures ---------------------------------------------------------------


class FakeService:
    """Doublure de `HistoryService` : retours pilotables + traçage des appels."""

    def __init__(
        self,
        records: list[SyncRecord] | None = None,
        logs: list[LogRecord] | None = None,
    ):
        self._records = records or []
        self._logs = logs or []
        self.get_sync_history_calls: list[tuple] = []
        self.get_operation_logs_calls: list[tuple] = []

    def get_sync_history(self, limit: int = 50) -> list[SyncRecord]:
        self.get_sync_history_calls.append((limit,))
        return list(self._records)

    def get_operation_logs(
        self,
        limit: int = 100,
        level: str | None = None,
    ) -> list[LogRecord]:
        self.get_operation_logs_calls.append((limit, level))
        if level is None:
            return list(self._logs)
        return [log for log in self._logs if log.level == level]


class Counter:
    """Compteur de notifications (substitut de callback de vue)."""

    def __init__(self):
        self.count = 0

    def __call__(self) -> None:
        self.count += 1


# --- Fabriques ---------------------------------------------------------------


def _record(
    record_id: int,
    file_count: int = 2,
    details: str | None = None,
    direction: str = "down",
    status: str = "success",
) -> SyncRecord:
    return SyncRecord(
        id=record_id,
        timestamp="2026-09-20 18:55:16",
        direction=direction,
        file_count=file_count,
        status=status,
        details=details,
    )


def _log(log_id: int, level: str = "INFO") -> LogRecord:
    return LogRecord(
        id=log_id,
        timestamp="2026-09-20 18:55:16",
        operation="sync.workouts",
        level=level,
        message="ok",
    )


# --- État initial ------------------------------------------------------------


@pytest.mark.unit
class TestInitialState:
    def test_empty_before_refresh(self) -> None:
        controller = HistoryController(FakeService())

        assert controller.records == []
        assert controller.logs == []
        assert controller.log_level_filter is None


# --- Refresh -----------------------------------------------------------------


@pytest.mark.unit
class TestRefresh:
    def test_loads_records_and_logs(self) -> None:
        service = FakeService(
            records=[_record(1), _record(2)],
            logs=[_log(1), _log(2, "ERROR")],
        )
        controller = HistoryController(service)

        controller.refresh()

        assert [r.id for r in controller.records] == [1, 2]
        assert [l.id for l in controller.logs] == [1, 2]
        assert service.get_sync_history_calls == [(50,)]
        assert service.get_operation_logs_calls == [(100, None)]

    def test_notifies_records_and_logs(self) -> None:
        controller = HistoryController(FakeService())
        records_cb = Counter()
        logs_cb = Counter()
        controller.on_records_changed(records_cb)
        controller.on_logs_changed(logs_cb)

        controller.refresh()

        assert records_cb.count == 1
        assert logs_cb.count == 1

    def test_refresh_respects_active_filter(self) -> None:
        service = FakeService(logs=[_log(1), _log(2, "ERROR")])
        controller = HistoryController(service)
        controller.set_log_level_filter("ERROR")
        service.get_operation_logs_calls.clear()  # on isole l'appel de refresh

        controller.refresh()

        assert service.get_operation_logs_calls == [(100, "ERROR")]


# --- Filtre de niveau --------------------------------------------------------


@pytest.mark.unit
class TestLogLevelFilter:
    def test_set_error_filter_reloads_logs(self) -> None:
        service = FakeService(logs=[_log(1), _log(2, "ERROR")])
        controller = HistoryController(service)
        logs_cb = Counter()
        controller.on_logs_changed(logs_cb)

        controller.set_log_level_filter("ERROR")

        assert controller.log_level_filter == "ERROR"
        assert [l.id for l in controller.logs] == [2]  # seuls les ERROR
        assert service.get_operation_logs_calls == [(100, "ERROR")]
        assert logs_cb.count == 1

    def test_set_none_filter_reloads_all(self) -> None:
        service = FakeService(logs=[_log(1), _log(2, "ERROR")])
        controller = HistoryController(service)
        controller.set_log_level_filter("ERROR")
        service.get_operation_logs_calls.clear()

        controller.set_log_level_filter(None)

        assert controller.log_level_filter is None
        assert [l.id for l in controller.logs] == [1, 2]
        assert service.get_operation_logs_calls == [(100, None)]

    def test_filter_does_not_reload_records(self) -> None:
        service = FakeService(records=[_record(1)])
        controller = HistoryController(service)
        controller.refresh()
        service.get_sync_history_calls.clear()

        controller.set_log_level_filter("WARN")

        assert service.get_sync_history_calls == []  # l'historique est inchangé


# --- Parsing du détail -------------------------------------------------------


@pytest.mark.unit
class TestParseRecord:
    def test_workout_format_without_skipped(self) -> None:
        controller = HistoryController(FakeService())
        record = _record(
            1,
            file_count=2,
            details='{"files": ["vma.fit", "10k_08.fit"], '
            '"errors": ["workout 123: RuntimeError: ..."]}',
        )

        detail = controller.parse_record(record)

        assert detail == SyncRecordDetail(
            files=("vma.fit", "10k_08.fit"),
            errors=("workout 123: RuntimeError: ...",),
            skipped=0,
            total=3,  # 2 réussis + 1 erreur
        )

    def test_activity_format_with_skipped(self) -> None:
        controller = HistoryController(FakeService())
        record = _record(
            1,
            file_count=1,
            details='{"files": ["2026-08-07-08-29-33.fit"], '
            '"errors": ["file Activity/ko.fit: ..."], "skipped": 1}',
        )

        detail = controller.parse_record(record)

        assert detail.files == ("2026-08-07-08-29-33.fit",)
        assert detail.errors == ("file Activity/ko.fit: ...",)
        assert detail.skipped == 1
        assert detail.total == 3  # 1 réussi + 1 erreur + 1 skippé

    def test_none_details_returns_empty(self) -> None:
        controller = HistoryController(FakeService())
        record = _record(1, file_count=2, details=None)

        detail = controller.parse_record(record)

        assert detail.files == ()
        assert detail.errors == ()
        assert detail.skipped == 0
        assert detail.total == 2  # ratio 2/2

    def test_invalid_json_returns_empty(self) -> None:
        controller = HistoryController(FakeService())
        record = _record(1, file_count=2, details="not valid json {")

        detail = controller.parse_record(record)

        assert detail.files == ()
        assert detail.errors == ()
        assert detail.skipped == 0
        assert detail.total == 2

    def test_non_dict_json_returns_empty(self) -> None:
        controller = HistoryController(FakeService())
        record = _record(1, file_count=2, details='["un", "tableau"]')

        detail = controller.parse_record(record)

        assert detail.files == ()
        assert detail.errors == ()
        assert detail.total == 2


# --- Copie défensive ---------------------------------------------------------


@pytest.mark.unit
class TestDefensiveCopy:
    def test_records_returns_copy(self) -> None:
        service = FakeService(records=[_record(1)])
        controller = HistoryController(service)
        controller.refresh()

        records = controller.records
        records.append(_record(2))

        assert [r.id for r in controller.records] == [1]


# --- Formatage du timestamp (UTC → local) ------------------------------------


@pytest.mark.unit
class TestFormatTimestamp:
    """Conversion UTC → heure locale du timestamp SQLite (option B du DP).

    Le schéma SQLite stocke les timestamps en UTC (`datetime('now')`, sans
    info de timezone). `format_timestamp` doit les convertir en heure locale
    avant de les reformater en `dd/mm/yyyy HH:MM`.
    """

    def test_utc_to_local_offset(self) -> None:
        """L'heure convertie = heure UTC + offset local exact."""
        utc_timestamp = "2026-09-21 10:13:00"

        result = HistoryController.format_timestamp(utc_timestamp)

        # Offset local (en secondes) de la machine qui exécute le test.
        # `datetime.now().astimezone().utcoffset()` tient compte de l'heure
        # d'été (DST) contrairement à `time.timezone`.
        utc_dt = datetime(2026, 9, 21, 10, 13, 0, tzinfo=timezone.utc)
        local_offset = datetime.now().astimezone().utcoffset()
        assert local_offset is not None  # mypy: l'offset est défini hors UTC pur.
        expected_local = utc_dt + local_offset
        expected = expected_local.strftime("%d/%m/%Y %H:%M")

        assert result == expected

    def test_output_format_structure(self) -> None:
        """La sortie respecte la structure `dd/mm/yyyy HH:MM` (15 caractères)."""
        result = HistoryController.format_timestamp("2026-09-21 10:13:00")

        # 10/09/2026 11:33 → 16 caractères ; on vérifie le motif par regex.
        # Format attendu : JJ/MM/AAAA HH:MM
        parts = result.split(" ")
        assert len(parts) == 2
        date_part, time_part = parts
        date_chunks = date_part.split("/")
        assert len(date_chunks) == 3
        assert all(chunk.isdigit() for chunk in date_chunks)
        time_chunks = time_part.split(":")
        assert len(time_chunks) == 2
        assert all(chunk.isdigit() for chunk in time_chunks)

    def test_invalid_format_returns_raw(self) -> None:
        """Un format inattendu est retourné tel quel (jamais d'exception)."""
        raw = "not a date"

        assert HistoryController.format_timestamp(raw) == raw

    def test_partial_format_returns_raw(self) -> None:
        """Un timestamp date seule (sans temps) échoue au parse → retour brut."""
        raw = "2026-09-21"

        assert HistoryController.format_timestamp(raw) == raw
