"""Historique des synchronisations (store Core) — ADR-002 / ADR-005.

Persiste chaque opération de sync dans `sync_history` (sens, nombre de fichiers,
statut, détails JSON libres) et la relit pour l'affichage de l'historique.

La colonne `details` est un `TEXT` libre : c'est le service appelant qui fournit
une chaîne déjà sérialisée en JSON (liste des fichiers, erreurs…). Le store
stocke la chaîne telle quelle, sans transformation.
"""

from __future__ import annotations

from dataclasses import dataclass

from openrunner55.store.database import Database

VALID_DIRECTIONS = frozenset({"up", "down", "both"})
VALID_STATUSES = frozenset({"success", "partial", "failed"})


@dataclass(frozen=True)
class SyncRecord:
    """Une entrée d'historique telle que retournée par `get_history`."""

    id: int
    timestamp: str
    direction: str
    file_count: int
    status: str
    details: str | None


class SyncHistoryStore:
    """Écrit et relit l'historique des synchronisations."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @staticmethod
    def _validate_direction(direction: str) -> None:
        if direction not in VALID_DIRECTIONS:
            raise ValueError(
                f"Direction invalide : {direction!r} "
                f"(attendu l'une de {sorted(VALID_DIRECTIONS)})"
            )

    @staticmethod
    def _validate_status(status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Statut invalide : {status!r} "
                f"(attendu l'un de {sorted(VALID_STATUSES)})"
            )

    def log_sync(
        self,
        direction: str,
        file_count: int,
        status: str,
        details: str | None = None,
    ) -> None:
        """Enregistre une synchronisation dans l'historique.

        :param direction: "up" | "down" | "both"
        :param file_count: nombre de fichiers concernés
        :param status: "success" | "partial" | "failed"
        :param details: chaîne JSON libre (liste des fichiers, erreurs…), ou None
        """
        self._validate_direction(direction)
        self._validate_status(status)
        conn = self._db.conn
        conn.execute(
            "INSERT INTO sync_history (direction, file_count, status, details)"
            " VALUES (?, ?, ?, ?)",
            (direction, file_count, status, details),
        )
        conn.commit()

    def get_history(self, limit: int = 50) -> list[SyncRecord]:
        """Retourne les `limit` dernières syncs, de la plus récente à la plus ancienne."""
        rows = self._db.conn.execute(
            "SELECT id, timestamp, direction, file_count, status, details"
            " FROM sync_history ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            SyncRecord(
                row["id"],
                row["timestamp"],
                row["direction"],
                row["file_count"],
                row["status"],
                row["details"],
            )
            for row in rows
        ]
