"""Test de non-régression : écriture SQLite cross-thread (bug E3).

La connexion SQLite est ouverte sur le thread GTK (`ui/app.py` via `db.connect()`)
mais les écritures de `push_workouts` (`sync/workouts.py`) surviennent dans un
thread worker daemon (`WorkoutsController._push_worker`). Avec le défaut
`check_same_thread=True` de `sqlite3.connect`, toute écriture depuis le worker
lève `sqlite3.ProgrammingError` et la base reste vide (`transferred_files`,
`sync_history`, `operation_logs` vides — bug E3).

Fix (ADR-005 révisé) : `check_same_thread=False` à l'ouverture. Sûr car un seul
écrivain à la fois (le worker de push) + verrou interne SQLite. Voir
`docs/decisions/adr-005.md`.

Ce test reproduit le scénario runtime (connect sur le thread principal, write
depuis un worker) et sert de non-régression : retirer `check_same_thread=False`
le ferait échouer (le worker lèverait `ProgrammingError`).
"""

from __future__ import annotations

import threading

import pytest

from openrunner55.store.database import Database


@pytest.mark.unit
class TestDatabaseCrossThread:
    def test_write_from_worker_thread_succeeds(self, tmp_path) -> None:
        """Une connexion ouverte sur le thread principal est écrivable depuis un worker.

        Reproduit le bug E3 : `db.connect()` sur le thread GTK, puis
        `mark_transferred` / `log_sync` exécutés dans le thread worker de
        `push_workouts`. Sans `check_same_thread=False`, le worker lèverait
        `ProgrammingError` et la base resterait vide. On écrit ici dans
        `operation_logs` (une des tables vides dans le bug) via le worker, puis
        on relit depuis le thread principal.
        """
        db = Database(tmp_path / "cross_thread.db")
        db.connect()
        try:
            errors: list[BaseException] = []

            def worker() -> None:
                try:
                    db.conn.execute(
                        "INSERT INTO operation_logs (level, message) "
                        "VALUES ('INFO', 'from worker')"
                    )
                    db.conn.commit()
                except BaseException as exc:  # noqa: BLE001 — remontée vers le thread principal
                    errors.append(exc)

            t = threading.Thread(target=worker, name="push-worker")
            t.start()
            t.join()

            assert not errors, f"le worker a levé une exception: {errors!r}"
            row = db.conn.execute(
                "SELECT level, message FROM operation_logs"
            ).fetchone()
            assert row is not None
            assert row["level"] == "INFO"
            assert row["message"] == "from worker"
        finally:
            db.close()
