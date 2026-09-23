"""Tests unitaires du SyncHistoryStore (store Core) — SQLite :memory:.

Voir docs/decisions/adr-002.md et adr-005.md (table `sync_history`) et adr-008.md.
"""

from __future__ import annotations

import pytest

from openrunner55.store.database import Database
from openrunner55.store.history import SyncHistoryStore, SyncRecord


@pytest.fixture
def history():
    db = Database(":memory:")
    db.connect()
    try:
        yield db, SyncHistoryStore(db)
    finally:
        db.close()


@pytest.mark.unit
class TestLogSync:
    def test_persists_entry(self, history) -> None:
        _, store = history
        store.log_sync("down", 3, "success")
        records = store.get_history()
        assert len(records) == 1
        assert records[0].direction == "down"
        assert records[0].file_count == 3
        assert records[0].status == "success"
        assert records[0].details is None

    def test_details_stored(self, history) -> None:
        _, store = history
        store.log_sync("down", 1, "partial", details='{"files": ["a.FIT"]}')
        assert store.get_history()[0].details == '{"files": ["a.FIT"]}'

    def test_direction_both_accepted(self, history) -> None:
        _, store = history
        store.log_sync("both", 5, "success")
        assert store.get_history()[0].direction == "both"

    def test_invalid_direction_raises(self, history) -> None:
        _, store = history
        with pytest.raises(ValueError):
            store.log_sync("sideways", 1, "success")

    def test_invalid_status_raises(self, history) -> None:
        _, store = history
        with pytest.raises(ValueError):
            store.log_sync("down", 1, "meh")


@pytest.mark.unit
class TestGetHistory:
    def test_most_recent_first(self, history) -> None:
        _, store = history
        store.log_sync("down", 1, "success")
        store.log_sync("up", 2, "success")
        records = store.get_history()
        assert len(records) == 2
        assert records[0].direction == "up"  # le plus récent d'abord
        assert records[0].id > records[1].id

    def test_respects_limit(self, history) -> None:
        _, store = history
        for i in range(5):
            store.log_sync("down", i, "success")
        assert len(store.get_history(limit=2)) == 2

    def test_default_limit_is_fifty(self, history) -> None:
        _, store = history
        for i in range(3):
            store.log_sync("down", i, "success")
        assert len(store.get_history()) == 3

    def test_empty_history(self, history) -> None:
        _, store = history
        assert store.get_history() == []

    def test_records_are_frozen_dataclass(self, history) -> None:
        _, store = history
        store.log_sync("down", 1, "success")
        record = store.get_history()[0]
        assert isinstance(record, SyncRecord)
        with pytest.raises(Exception):
            record.status = "failed"  # dataclass frozen
