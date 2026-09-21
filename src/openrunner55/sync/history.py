"""Service de consultation de l'historique et des logs (couche Services).

`HistoryService` est le **seul** point d'entrée que l'UI est autorisée à
appeler pour consulter l'historique des synchronisations et les logs
d'opération (ADR-002, règle cardinale UI → Services → Core). C'est un wrapper
fin en lecture seule autour des stores Core `SyncHistoryStore` et
`OperationLogger` : il ne réimplémente aucune logique métier, ne filtre rien,
ne parse rien. Le filtrage anti-credentials est déjà appliqué en amont par
`OperationLogger` (ENF-4) — transparent pour ce service et pour l'UI.
"""

from __future__ import annotations

from openrunner55.store.history import SyncHistoryStore, SyncRecord
from openrunner55.store.logger import LogRecord, OperationLogger


class HistoryService:
    """Service de consultation de l'historique et des logs (ADR-002).

    Interface en lecture seule pour l'UI. Wrappe les stores Core
    (`SyncHistoryStore`, `OperationLogger`) sans ajouter de logique métier.
    """

    def __init__(self, history: SyncHistoryStore, logger: OperationLogger) -> None:
        self._history = history
        self._logger = logger

    def get_sync_history(self, limit: int = 50) -> list[SyncRecord]:
        """Retourne les dernières syncs, de la plus récente à la plus ancienne.

        :param limit: nombre maximum d'entrées à retourner.
        """
        return self._history.get_history(limit)

    def get_operation_logs(
        self,
        limit: int = 100,
        level: str | None = None,
    ) -> list[LogRecord]:
        """Retourne les logs, filtrables par niveau (INFO/WARN/ERROR).

        :param limit: nombre maximum d'entrées à retourner.
        :param level: "INFO" | "WARN" | "ERROR" | None (tous niveaux).
        """
        return self._logger.get_logs(limit=limit, level=level)
