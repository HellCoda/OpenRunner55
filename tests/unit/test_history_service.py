"""Tests unitaires du `HistoryService` (couche Services, wrapper fin).

Voir docs/decisions/adr-002.md (architecture 3 couches) et adr-008.md
(stratégie de tests). Le service délègue en lecture seule aux stores Core
`SyncHistoryStore` et `OperationLogger` ; les tests vérifient uniquement la
délégation (bonne méthode appelée, bons arguments transmis, résultat propagé
tel quel), avec des doublures pilotables.
"""

from __future__ import annotations

import pytest

from openrunner55.store.history import SyncRecord
from openrunner55.store.logger import LogRecord
from openrunner55.sync.history import HistoryService


# --- Doublures ---------------------------------------------------------------


class FakeHistoryStore:
    """Doublure de `SyncHistoryStore` : retour pilotable + traçage des appels."""

    def __init__(self, records: list[SyncRecord] | None = None):
        self._records = records or []
        self.get_history_calls: list[tuple] = []

    def get_history(self, limit: int = 50) -> list[SyncRecord]:
        self.get_history_calls.append((limit,))
        return list(self._records)


class FakeOperationLogger:
    """Doublure de `OperationLogger` : retour pilotable + traçage des appels."""

    def __init__(self, logs: list[LogRecord] | None = None):
        self._logs = logs or []
        self.get_logs_calls: list[tuple] = []

    def get_logs(
        self,
        limit: int = 100,
        level: str | None = None,
        operation: str | None = None,
    ) -> list[LogRecord]:
        self.get_logs_calls.append((limit, level))
        return list(self._logs)


def _make_record(record_id: int) -> SyncRecord:
    return SyncRecord(
        id=record_id,
        timestamp="2026-09-20 18:55:16",
        direction="down",
        file_count=2,
        status="success",
        details='{"files": ["a.fit", "b.fit"]}',
    )


def _make_log(log_id: int, level: str = "INFO") -> LogRecord:
    return LogRecord(
        id=log_id,
        timestamp="2026-09-20 18:55:16",
        operation="sync.workouts",
        level=level,
        message="ok",
    )


# --- Tests -------------------------------------------------------------------


@pytest.mark.unit
class TestGetSyncHistory:
    def test_delegates_to_history_store(self) -> None:
        history = FakeHistoryStore([_make_record(1), _make_record(2)])
        service = HistoryService(history, FakeOperationLogger())

        result = service.get_sync_history()

        assert history.get_history_calls == [(50,)]
        assert result == [_make_record(1), _make_record(2)]

    def test_forwards_limit(self) -> None:
        history = FakeHistoryStore([_make_record(1)])
        service = HistoryService(history, FakeOperationLogger())

        service.get_sync_history(limit=10)

        assert history.get_history_calls == [(10,)]

    def test_returns_empty_list_as_is(self) -> None:
        history = FakeHistoryStore([])
        service = HistoryService(history, FakeOperationLogger())

        assert service.get_sync_history() == []


@pytest.mark.unit
class TestGetOperationLogs:
    def test_delegates_to_operation_logger(self) -> None:
        logger = FakeOperationLogger([_make_log(1), _make_log(2, "ERROR")])
        service = HistoryService(FakeHistoryStore(), logger)

        result = service.get_operation_logs()

        assert logger.get_logs_calls == [(100, None)]
        assert result == [_make_log(1), _make_log(2, "ERROR")]

    def test_forwards_limit(self) -> None:
        logger = FakeOperationLogger([_make_log(1)])
        service = HistoryService(FakeHistoryStore(), logger)

        service.get_operation_logs(limit=25)

        assert logger.get_logs_calls == [(25, None)]

    def test_forwards_level_filter(self) -> None:
        logger = FakeOperationLogger([_make_log(1, "ERROR")])
        service = HistoryService(FakeHistoryStore(), logger)

        service.get_operation_logs(level="ERROR")

        assert logger.get_logs_calls == [(100, "ERROR")]

    def test_none_level_means_no_filter(self) -> None:
        logger = FakeOperationLogger([_make_log(1)])
        service = HistoryService(FakeHistoryStore(), logger)

        service.get_operation_logs(level=None)

        assert logger.get_logs_calls == [(100, None)]

    def test_returns_empty_list_as_is(self) -> None:
        logger = FakeOperationLogger([])
        service = HistoryService(FakeHistoryStore(), logger)

        assert service.get_operation_logs() == []
