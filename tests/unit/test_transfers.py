"""Tests unitaires du TransferredFilesStore (store Core) — SQLite :memory:.

Voir docs/decisions/adr-005.md (schéma `transferred_files`) et adr-008.md.
"""

from __future__ import annotations

import pytest

from openrunner55.store.database import Database
from openrunner55.store.transfers import TransferredFilesStore


@pytest.fixture
def transferred():
    db = Database(":memory:")
    db.connect()
    try:
        yield db, TransferredFilesStore(db)
    finally:
        db.close()


@pytest.mark.unit
class TestIsTransferred:
    def test_false_initially(self, transferred) -> None:
        _, store = transferred
        assert store.is_transferred("foo.FIT", "down") is False

    def test_true_after_mark(self, transferred) -> None:
        _, store = transferred
        store.mark_transferred("foo.FIT", "down", "workout")
        assert store.is_transferred("foo.FIT", "down") is True

    def test_direction_is_discriminating(self, transferred) -> None:
        _, store = transferred
        store.mark_transferred("foo.FIT", "down", "workout")
        assert store.is_transferred("foo.FIT", "up") is False

    def test_without_source_ignores_source(self, transferred) -> None:
        _, store = transferred
        store.mark_transferred("foo.FIT", "down", "workout")
        # Sans source : toute source est acceptée (contrat brief).
        assert store.is_transferred("foo.FIT", "down") is True

    def test_with_source_filters_precisely(self, transferred) -> None:
        _, store = transferred
        store.mark_transferred("foo.FIT", "down", "workout")
        assert store.is_transferred("foo.FIT", "down", "workout") is True
        assert store.is_transferred("foo.FIT", "down", "activity") is False


@pytest.mark.unit
class TestMarkTransferred:
    def test_persists_row(self, transferred) -> None:
        db, store = transferred
        store.mark_transferred("foo.FIT", "down", "workout")
        row = db.conn.execute(
            "SELECT file_name, direction, source, gc_activity_id, file_hash"
            " FROM transferred_files"
        ).fetchone()
        assert row["file_name"] == "foo.FIT"
        assert row["direction"] == "down"
        assert row["source"] == "workout"
        assert row["gc_activity_id"] is None
        assert row["file_hash"] is None  # NULL au MVP (ADR-005)

    def test_gc_activity_id_persisted(self, transferred) -> None:
        db, store = transferred
        store.mark_transferred("foo.FIT", "up", "activity", gc_activity_id=42)
        row = db.conn.execute(
            "SELECT gc_activity_id FROM transferred_files"
        ).fetchone()
        assert row["gc_activity_id"] == 42


@pytest.mark.unit
class TestValidation:
    def test_mark_invalid_direction_raises(self, transferred) -> None:
        _, store = transferred
        with pytest.raises(ValueError):
            store.mark_transferred("foo.FIT", "sideways", "workout")

    def test_mark_invalid_source_raises(self, transferred) -> None:
        _, store = transferred
        with pytest.raises(ValueError):
            store.mark_transferred("foo.FIT", "down", "nope")

    def test_is_transferred_invalid_direction_raises(self, transferred) -> None:
        _, store = transferred
        with pytest.raises(ValueError):
            store.is_transferred("foo.FIT", "sideways")

    def test_is_transferred_invalid_source_raises(self, transferred) -> None:
        _, store = transferred
        with pytest.raises(ValueError):
            store.is_transferred("foo.FIT", "down", source="nope")
