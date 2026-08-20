"""Connexion SQLite et création des tables (store Core).

Note de divergence ADR-005 : l'ADR place la base dans `~/.config/openrunner55/`.
La convention XDG réserve `~/.config` à la configuration (le tokenstore y est
déjà) et `~/.local/share` aux données applicatives. La base étant une donnée
d'application, nous suivons la mission Epic 1 (`~/.local/share`) — à acter
dans une révision d'ADR.

Le module expose la classe `Database` qui gère la connexion, la création du
schéma et une version de schéma pour de futures migrations légères.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("~/.local/share/openrunner55/openrunner.db").expanduser()
SCHEMA_VERSION = 2

_SCHEMA = """
-- Historique des synchronisations
CREATE TABLE IF NOT EXISTS sync_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT    NOT NULL DEFAULT (datetime('now')),
    direction  TEXT    NOT NULL CHECK (direction IN ('up', 'down', 'both')),
    file_count INTEGER NOT NULL DEFAULT 0,
    status     TEXT    NOT NULL CHECK (status IN ('success', 'partial', 'failed')),
    details    TEXT              -- JSON libre : liste des fichiers, erreurs
);

-- Logs d'opération
CREATE TABLE IF NOT EXISTS operation_logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT    NOT NULL DEFAULT (datetime('now')),
    operation TEXT    NOT NULL DEFAULT '',
    level     TEXT    NOT NULL DEFAULT 'INFO' CHECK (level IN ('DEBUG', 'INFO', 'WARN', 'ERROR')),
    message   TEXT    NOT NULL
);

-- Fichiers déjà transférés (déduplication locale)
CREATE TABLE IF NOT EXISTS transferred_files (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name      TEXT    NOT NULL,
    file_hash      TEXT,              -- SHA256 du contenu (optionnel, MVP : NULL)
    direction      TEXT    NOT NULL CHECK (direction IN ('up', 'down')),
    source         TEXT    NOT NULL CHECK (source IN ('activity', 'monitor', 'sleep', 'metrics', 'workout')),
    transferred_at TEXT    NOT NULL DEFAULT (datetime('now')),
    gc_activity_id BIGINT             -- ID côté GC si applicable (upload)
);
"""


class Database:
    """Connexion SQLite avec gestion du schéma.

    Utilisation recommandée en contexte (`with`) : la connexion est fermée à
    la sortie du bloc.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_DB_PATH
        self._conn: sqlite3.Connection | None = None

    # -- cycle de vie -------------------------------------------------------

    def connect(self) -> sqlite3.Connection:
        """Ouvre (et crée si besoin) la base, applique le schéma, retourne la connexion."""
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False : la connexion est ouverte sur le thread GTK
        # (ui/app.py) mais les écritures de push_workouts surviennent dans un
        # thread worker (WorkoutsController._push_worker). Le défaut True y lève
        # sqlite3.ProgrammingError et laisse la base vide (bug E3). Sûr car un
        # seul écrivain à la fois + verrou interne SQLite. Voir ADR-005 (révisé).
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        return self._conn

    def close(self) -> None:
        """Ferme la connexion si elle est ouverte."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database non connectée : appeler connect() d'abord")
        return self._conn

    # -- schéma -------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_version (
                   version INTEGER NOT NULL
               )"""
        )
        row = self._conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            self._conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
            self._conn.commit()
        elif row["version"] > SCHEMA_VERSION:
            raise RuntimeError(
                f"Base plus récente que le code (v{row['version']} > v{SCHEMA_VERSION})"
            )
        self._migrate(row["version"] if row is not None else SCHEMA_VERSION)

    def _migrate(self, from_version: int) -> None:
        """Applique les migrations légères (ADR-005) et met à jour la version."""
        if from_version < 2:
            # v1 → v2 : colonne operation dans operation_logs (tracabilité des logs)
            columns = {
                c["name"] for c in self._conn.execute("PRAGMA table_info(operation_logs)")
            }
            if "operation" not in columns:
                self._conn.execute(
                    "ALTER TABLE operation_logs ADD COLUMN operation TEXT NOT NULL DEFAULT ''"
                )
            self._conn.execute(
                "UPDATE schema_version SET version = ?", (SCHEMA_VERSION,)
            )
            self._conn.commit()
