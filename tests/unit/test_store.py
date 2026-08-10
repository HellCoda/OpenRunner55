"""Tests unitaires du store Core (SQLite en :memory:).

Voir docs/decisions/adr-005.md et adr-008.md.
"""

from __future__ import annotations

import sqlite3

import pytest

from openrunner55.store.database import Database
from openrunner55.store.logger import LogRecord, OperationLogger


@pytest.mark.unit
class TestDatabase:
    def test_connect_creates_tables(self) -> None:
        """La connexion crée les trois tables métier + schema_version."""
        db = Database(":memory:")
        db.connect()
        try:
            tables = {
                row["name"]
                for row in db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"sync_history", "operation_logs", "transferred_files", "schema_version"} <= tables
        finally:
            db.close()

    def test_schema_version_is_set(self) -> None:
        db = Database(":memory:")
        db.connect()
        try:
            version = db.conn.execute("SELECT version FROM schema_version").fetchone()["version"]
            assert version == 1
        finally:
            db.close()

    def test_row_factory_enabled(self) -> None:
        db = Database(":memory:")
        db.connect()
        try:
            row = db.conn.execute("SELECT 1 AS value").fetchone()
            assert row["value"] == 1  # accès par nom => row_factory actif
        finally:
            db.close()

    def test_context_manager_closes_connection(self) -> None:
        with Database(":memory:") as db:
            conn = db.conn
            assert conn is not None
        with pytest.raises(RuntimeError):
            _ = db.conn  # connexion fermée

    def test_physical_file_is_created(self, tmp_path) -> None:
        path = tmp_path / "data" / "openrunner.db"
        db = Database(path)
        db.connect()
        db.close()
        assert path.is_file()

    def test_default_path_under_local_share(self) -> None:
        from pathlib import Path

        from openrunner55.store import database as db_mod

        expanded = db_mod.DEFAULT_DB_PATH.expanduser()
        assert expanded.is_absolute()
        # Relatif au HOME, la base doit être dans .local/share (pas .config)
        relative = expanded.relative_to(Path.home())
        assert relative.parts[0] == ".local"
        assert "share" in relative.parts
        assert relative.name == "openrunner.db"

    def test_connect_twice_is_safe(self) -> None:
        db = Database(":memory:")
        db.connect()
        try:
            db.connect()  # réentrant : remplace la connexion sans erreur
        finally:
            db.close()


@pytest.mark.unit
class TestOperationLogger:
    def _make_logger(self) -> tuple[Database, OperationLogger]:
        db = Database(":memory:")
        db.connect()
        return db, OperationLogger(db)

    def test_log_persists_entry(self) -> None:
        db, logger = self._make_logger()
        try:
            logger.log("sync.upload", "ok", "3 fichiers uploadés")
            rows = logger.get_logs()
            assert len(rows) == 1
            assert rows[0].level == "INFO"
            assert "3 fichiers uploadés" in rows[0].message
        finally:
            db.close()

    def test_status_maps_to_level(self) -> None:
        db, logger = self._make_logger()
        try:
            logger.log("auth.login", "ok", "connexion réussie")
            logger.log("sync.download", "warning", "1 fichier en échec")
            logger.log("sync.upload", "error", "upload impossible")
            levels = {r.level for r in logger.get_logs(limit=10)}
            assert levels == {"INFO", "WARN", "ERROR"}
        finally:
            db.close()

    def test_get_logs_filters_by_level(self) -> None:
        db, logger = self._make_logger()
        try:
            logger.log("op1", "ok", "message info")
            logger.log("op2", "error", "message erreur")
            errors = logger.get_logs(level="ERROR")
            assert len(errors) == 1
            assert errors[0].level == "ERROR"
            assert "message erreur" in errors[0].message
        finally:
            db.close()

    def test_get_logs_respects_limit(self) -> None:
        db, logger = self._make_logger()
        try:
            for i in range(5):
                logger.log("op", "ok", f"message {i}")
            rows = logger.get_logs(limit=2)
            assert len(rows) == 2
            # ordre anti-chronologique : les plus récents d'abord
            assert rows[0].id > rows[1].id
        finally:
            db.close()

    def test_get_logs_invalid_level(self) -> None:
        db, logger = self._make_logger()
        try:
            logger.log("op", "ok", "message")
            with pytest.raises(ValueError):
                logger.get_logs(level="NOT_A_LEVEL")
        finally:
            db.close()

    def test_returned_records_are_immutable(self) -> None:
        db, logger = self._make_logger()
        try:
            logger.log("op", "ok", "message")
            record = logger.get_logs()[0]
            assert isinstance(record, LogRecord)
            with pytest.raises(Exception):
                record.level = "ERROR"  # dataclass frozen
        finally:
            db.close()


@pytest.mark.unit
class TestRedactFilter:
    def test_email_is_redacted(self) -> None:
        assert (
            OperationLogger.redact("Login de user@example.com réussi")
            == "Login de [REDACTED] réussi"
        )

    def test_password_value_is_redacted(self) -> None:
        assert (
            OperationLogger.redact("password=motdepasse123")
            == "password=[REDACTED]"
        )

    def test_password_with_spaces_is_redacted(self) -> None:
        assert (
            OperationLogger.redact('mot de passe: "secret secret"')
            == "mot de passe: [REDACTED]"
        )

    def test_pwd_key_is_redacted(self) -> None:
        assert (
            OperationLogger.redact("pwd = azerty")
            == "pwd = [REDACTED]"
        )

    def test_token_value_is_redacted(self) -> None:
        assert (
            OperationLogger.redact("token=eyJhbGciOi.abc.def")
            == "token=[REDACTED]"
        )

    def test_multiple_credentials_in_one_message(self) -> None:
        out = OperationLogger.redact("user@example.com password=secret")
        assert out == "[REDACTED] password=[REDACTED]"

    def test_plain_message_unchanged(self) -> None:
        msg = "3 workouts synchronisés vers la montre"
        assert OperationLogger.redact(msg) == msg

    def test_empty_message(self) -> None:
        assert OperationLogger.redact("") == ""
        assert OperationLogger.redact(None) is None

    def test_log_applies_filter_before_persist(self) -> None:
        db = Database(":memory:")
        db.connect()
        try:
            logger = OperationLogger(db)
            logger.log("auth.login", "ok", "connexion de user@example.com password=secret")
            stored = logger.get_logs()[0].message
            assert "user@example.com" not in stored
            assert "secret" not in stored
            assert "[REDACTED]" in stored
        finally:
            db.close()
