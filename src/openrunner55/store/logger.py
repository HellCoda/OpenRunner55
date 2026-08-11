"""Logger d'opérations persisté dans `operation_logs` (store Core).

Conforme ENF-4 : aucun credential ne doit apparaître dans les logs. Le module
applique un filtre anti-credentials sur chaque message avant insertion en base
(patterns email et clé=valeur sensibles remplacés par [REDACTED]).

API d'écriture selon la mission Epic 1 : `log(operation, status, message)`.
Le niveau est dérivé du status (ok → INFO, warning → WARN, erreur → ERROR).
API de lecture selon ADR-002 : `get_logs(limit, level)` — c'est l'interface
qu'exposera le service `sync/history.py` à l'UI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from openrunner55.store.database import Database

# Pattern email : identifiant@domaine.tld
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Pattern clé=valeur sensible : password=xxx, "mot de passe": xxx, etc.
# Le groupe 1 capture clé + séparateur (préserve ":" ou "=" et les espaces),
# le groupe 2 la valeur à masquer.
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(\b(?:password|passwd|pwd|mdp|mot\s*de\s*passe|secret|token)"
    r"\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
)

_VALID_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}

_REDACTED = "[REDACTED]"

_STATUS_LEVELS = {
    "ok": "INFO",
    "success": "INFO",
    "warning": "WARN",
    "warn": "WARN",
    "partial": "WARN",
    "error": "ERROR",
    "failed": "ERROR",
    "fail": "ERROR",
}


@dataclass(frozen=True)
class LogRecord:
    """Une entrée de log telle que retournée par `get_logs`."""

    id: int
    timestamp: str
    operation: str
    level: str
    message: str


class OperationLogger:
    """Écriture et lecture des logs d'opération persistés."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # -- filtre anti-credentials --------------------------------------------

    @staticmethod
    def redact(message: str) -> str:
        """Masque les credentials éventuels d'un message (conformité ENF-4)."""
        if not message:
            return message
        message = _EMAIL_PATTERN.sub(_REDACTED, message)
        return _SENSITIVE_VALUE_PATTERN.sub(
            lambda m: f"{m.group(1)}{_REDACTED}", message
        )

    # -- écriture -----------------------------------------------------------

    def log(self, operation: str, status: str, message: str) -> None:
        """Persiste une opération dans `operation_logs`.

        :param operation: nom court de l'opération (ex: "auth.login", "sync.upload")
        :param status: résultat (ok, warning, error…) — dérive le niveau
        :param message: détail lisible, passé au filtre anti-credentials
        """
        level = _STATUS_LEVELS.get(status.lower(), "INFO")
        safe_message = self.redact(message)
        conn = self._db.conn
        conn.execute(
            "INSERT INTO operation_logs (operation, level, message) VALUES (?, ?, ?)",
            (operation, level, safe_message),
        )
        conn.commit()

    # -- lecture ------------------------------------------------------------

    def get_logs(
        self,
        limit: int = 100,
        level: str | None = None,
        operation: str | None = None,
    ) -> list[LogRecord]:
        """Retourne les logs les plus récents, filtrables par niveau et/ou opération.

        :param level: "DEBUG" | "INFO" | "WARN" | "ERROR" | None (tous niveaux)
        :param operation: nom d'opération exact (ex: "auth.login") | None (toutes)
        """
        query = "SELECT id, timestamp, operation, level, message FROM operation_logs"
        params: list[object] = []
        if level is not None:
            if level.upper() not in _VALID_LEVELS:
                raise ValueError(f"Niveau invalide : {level!r} (attendu DEBUG|INFO|WARN|ERROR)")
            query += " WHERE level = ?"
            params.append(level.upper())
        if operation is not None:
            query += " WHERE operation = ?" if " WHERE " not in query else " AND operation = ?"
            params.append(operation)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        rows = self._db.conn.execute(query, params).fetchall()
        return [
            LogRecord(r["id"], r["timestamp"], r["operation"], r["level"], r["message"])
            for r in rows
        ]
