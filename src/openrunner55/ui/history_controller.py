"""Logique de présentation de la section Logs & Historique (couche UI, sans GTK).

`HistoryController` extrait de la vue GTK toute la logique testable
unitairement : état de l'historique, état des logs, filtre de niveau actif,
parsing du JSON `details` et calcul du ratio (réussis/total). Il ne touche
jamais aux widgets — il expose un état et des callbacks ; la vue s'abonne et
rafraîchit l'interface quand un callback est déclenché (pattern observateur,
miroir de `WorkoutsController` / `ActivitiesController`).

Contraintes d'architecture (ADR-002) :

- **Pas d'import de `gi.repository`** : le controller est testable avec des
  doublures, sans boucle GTK.
- **Pas d'import de `store/` directement** : les records (`SyncRecord`,
  `LogRecord`) et le service (`HistoryService`) sont importés depuis la couche
  Services `sync/history.py` — jamais depuis le Core.
- **Toute la logique métier vient du Service** `sync/history.py`
  (`get_sync_history`, `get_operation_logs`). Le parsing du champ `details`
  est de la logique de présentation (affichage du détail), pas de la logique
  métier : il reste ici, conformément au brief.

Threading : néant. Les lectures SQLite sont instantanées (50-100 lignes,
`check_same_thread=False`). `refresh()` et `set_log_level_filter()` sont
synchrones. Si une latence apparaît avec de gros volumes, on threadera plus
tard (décision du brief).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from openrunner55.sync.history import HistoryService, LogRecord, SyncRecord


@dataclass(frozen=True)
class SyncRecordDetail:
    """Détail parsé d'une entrée d'historique (pour l'affichage du détail).

    - `files` : noms des fichiers réussis (affichés avec ✓).
    - `errors` : messages d'erreur (affichés avec ✗).
    - `skipped` : nombre de fichiers déjà transférés (skippés), 0 par défaut.
    - `total` : nombre total de fichiers concernés, calculé
      `file_count + len(errors) + skipped` (le ratio affiché est
      `file_count / total`).
    """

    files: tuple[str, ...]
    errors: tuple[str, ...]
    skipped: int
    total: int


class HistoryController:
    """Logique de présentation de la section Logs & Historique (sans GTK).

    :param service: `HistoryService` (couche Services) — seule interface de
        consultation de l'historique et des logs, injectée par la composition
        root (ADR-002).
    """

    def __init__(self, service: HistoryService) -> None:
        self._service = service

        # -- état --
        self._records: list[SyncRecord] = []
        self._logs: list[LogRecord] = []
        self._log_level_filter: str | None = None

        # -- callbacks de la vue --
        self._on_records_changed_cb: Callable[[], None] | None = None
        self._on_logs_changed_cb: Callable[[], None] | None = None

    # -- état ----------------------------------------------------------------

    @property
    def records(self) -> list[SyncRecord]:
        """Liste des syncs affichées (plus récentes en premier, copie défensive)."""
        return list(self._records)

    @property
    def logs(self) -> list[LogRecord]:
        """Liste des logs affichés (copie défensive)."""
        return list(self._logs)

    @property
    def log_level_filter(self) -> str | None:
        """Filtre de niveau actif (None = tous niveaux)."""
        return self._log_level_filter

    # -- actions -------------------------------------------------------------

    def refresh(self) -> None:
        """Recharge l'historique et les logs depuis le service.

        Les logs sont rechargés en respectant le filtre de niveau actif.
        Notifie la vue via `on_records_changed` puis `on_logs_changed`.
        """
        self._records = self._service.get_sync_history()
        self._logs = self._service.get_operation_logs(level=self._log_level_filter)
        self._notify_records_changed()
        self._notify_logs_changed()

    def set_log_level_filter(self, level: str | None) -> None:
        """Définit le filtre de niveau des logs et recharge les logs filtrés.

        :param level: "INFO" | "WARN" | "ERROR" | None (tous niveaux).
        """
        self._log_level_filter = level
        self._logs = self._service.get_operation_logs(level=level)
        self._notify_logs_changed()

    # -- parsing du détail (logique de présentation) -------------------------

    @staticmethod
    def format_timestamp(timestamp: str) -> str:
        """Formate un timestamp SQLite en heure locale « dd/mm/yyyy HH:MM ».

        Le schéma SQLite utilise `DEFAULT (datetime('now'))` qui produit un
        timestamp **UTC** au format `YYYY-MM-DD HH:MM:SS` (sans info de
        timezone). On le parse donc comme UTC, puis on convertit en heure
        locale du système avant de reformater.

        :param timestamp: chaîne SQLite `YYYY-MM-DD HH:MM:SS` (comprise
            comme UTC). Tout autre format est retourné tel quel.
        :returns: `dd/mm/yyyy HH:MM` en heure locale, ou la chaîne brute si
            le format est inattendu (jamais d'exception).
        """
        try:
            dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return timestamp
        local_dt = dt.replace(tzinfo=timezone.utc).astimezone()
        return local_dt.strftime("%d/%m/%Y %H:%M")

    def parse_record(self, record: SyncRecord) -> SyncRecordDetail:
        """Parse le JSON `details` d'un `SyncRecord` et calcule le total.

        Robustesse : `details` à `None` ou JSON malformé → détail vide
        (`files=()`, `errors=()`, `skipped=0`) et `total = record.file_count`
        (ratio `file_count / file_count`). Ne lève jamais.

        :param record: entrée d'historique à détailler.
        """
        files: tuple[str, ...] = ()
        errors: tuple[str, ...] = ()
        skipped = 0

        if record.details:
            data: object | None = None
            try:
                data = json.loads(record.details)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, dict):
                raw_files = data.get("files")
                raw_errors = data.get("errors")
                raw_skipped = data.get("skipped")
                if isinstance(raw_files, list):
                    files = tuple(str(f) for f in raw_files)
                if isinstance(raw_errors, list):
                    errors = tuple(str(e) for e in raw_errors)
                if isinstance(raw_skipped, int):
                    skipped = raw_skipped

        total = record.file_count + len(errors) + skipped
        return SyncRecordDetail(
            files=files,
            errors=errors,
            skipped=skipped,
            total=total,
        )

    # -- callbacks de la vue (à connecter) -----------------------------------

    def on_records_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand l'historique change."""
        self._on_records_changed_cb = callback

    def on_logs_changed(self, callback: Callable[[], None]) -> None:
        """Enregistre le callback notifié quand les logs changent (ou le filtre)."""
        self._on_logs_changed_cb = callback

    # -- internes de notification -------------------------------------------

    def _notify_records_changed(self) -> None:
        if self._on_records_changed_cb is not None:
            self._on_records_changed_cb()

    def _notify_logs_changed(self) -> None:
        if self._on_logs_changed_cb is not None:
            self._on_logs_changed_cb()
