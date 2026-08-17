"""Déduplication locale des fichiers transférés (store Core) — ADR-005.

La table `transferred_files` garde trace des fichiers déjà copiés (direction
`down`) ou uploadés (`up`). La déduplication se fait sur
`(file_name, direction, source)` ; la colonne `file_hash` (SHA256) est prévue
par le schéma mais laissée NULL au MVP (ADR-005).

Écart assumé par rapport à ADR-005 : la méthode de lecture s'appelle
`is_transferred` (nom du brief Epic 2, contrat frontend) et non
`is_already_transferred` (ADR-005). Elle accepte un paramètre `source`
**optionnel** pour concilier les deux signatures : sans `source`, elle interroge
uniquement `(file_name, direction)` ; avec `source`, elle applique la
déduplication précise `(file_name, direction, source)` de l'ADR-005.

Note : `mark_transferred` insère sans contrainte d'unicité — marquer deux fois
le même fichier crée deux lignes (sans impact fonctionnel : `is_transferred`
retourne True dans les deux cas). Un index unique `(file_name, direction,
source)` pourra être ajouté via migration si le besoin se confirme.
"""

from __future__ import annotations

from openrunner55.store.database import Database

VALID_DIRECTIONS = frozenset({"up", "down"})
VALID_SOURCES = frozenset({"activity", "monitor", "sleep", "metrics", "workout"})


class TransferredFilesStore:
    """Marque et interroge les fichiers déjà transférés (déduplication)."""

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
    def _validate_source(source: str) -> None:
        if source not in VALID_SOURCES:
            raise ValueError(
                f"Source invalide : {source!r} "
                f"(attendu l'une de {sorted(VALID_SOURCES)})"
            )

    def mark_transferred(
        self,
        file_name: str,
        direction: str,
        source: str,
        gc_activity_id: int | None = None,
    ) -> None:
        """Marque un fichier comme déjà transféré (déduplication).

        :param direction: "up" | "down"
        :param source: "activity" | "monitor" | "sleep" | "metrics" | "workout"
        :param gc_activity_id: ID côté GC si applicable (upload), sinon None.
        """
        self._validate_direction(direction)
        self._validate_source(source)
        conn = self._db.conn
        conn.execute(
            "INSERT INTO transferred_files (file_name, direction, source, gc_activity_id)"
            " VALUES (?, ?, ?, ?)",
            (file_name, direction, source, gc_activity_id),
        )
        conn.commit()

    def is_transferred(
        self,
        file_name: str,
        direction: str,
        source: str | None = None,
    ) -> bool:
        """True si le fichier a déjà été transféré dans ce sens.

        :param source: si fourni, filtre sur la source (dédup précise ADR-005) ;
            si None, ignore la source (interroge `(file_name, direction)` seul).
        """
        self._validate_direction(direction)
        if source is not None:
            self._validate_source(source)
        query = "SELECT 1 FROM transferred_files WHERE file_name = ? AND direction = ?"
        params: list[object] = [file_name, direction]
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        query += " LIMIT 1"
        return self._db.conn.execute(query, params).fetchone() is not None
