"""Lecture/écriture des fichiers FIT sur la montre FR55 (watch Core) — ADR-002.

`WatchFilesystem` est construit sur le point de montage du volume (ex.
`/run/media/$USER/GARMIN`) et travaille sur la racine des données Garmin
`{mount_path}/GARMIN/` (cf. `docs/exploration/tree-FR55.md`).

**Convention de chemin :** les méthodes qui prennent ou retournent un `Path`
manipulent des chemins **relatifs à la racine GARMIN/** (ex.
`Path("Workouts/mon_workout.FIT")`). Ainsi un chemin retourné par
`list_fit_files()` peut être passé directement à `read_fit()`/`write_fit()`.
Le module ne connaît ni Garmin ni la logique de nommage (slugify) : il reçoit
un chemin et écrit des bytes (ADR-002).

**Erreurs :** `write_fit` crée le dossier parent si nécessaire et **lève
`OSError`** en cas d'échec (déconnexion USB, permissions, volume en lecture
seule). Pas de booléen silencieux : c'est le service appelant qui décide de la
stratégie (continuer au suivant vs abort).

**Extension `.FIT` :** le système de fichiers de la montre est en FAT32
(casse-insensible). Les fichiers portent indifféremment l'extension `.fit` ou
`.FIT` (cf. tree-FR55) : `list_fit_files` filtre de façon insensible à la casse.

Note (écart ADR-002) : l'ADR liste `write_fit(...) -> bool` ; le brief Epic 2 le
remplace par `-> None` + levée `OSError` (plus explicite qu'un booléen).
"""

from __future__ import annotations

from pathlib import Path

# Catégories de dossiers FIT gérées (cf. ADR-002 et tree-FR55).
VALID_CATEGORIES = frozenset({"Activity", "Workouts", "Monitor", "Sleep", "Metrics"})

# Racine des données Garmin au sein du volume monté.
GARMIN_DIR = "GARMIN"


class WatchFilesystem:
    """Accès en lecture/écriture aux dossiers FIT de la montre.

    :param mount_path: point de montage du volume (ex. `/run/media/$USER/GARMIN`).
        Injectable (ex. `tmp_path`) pour les tests sans montre.
    """

    def __init__(self, mount_path: Path) -> None:
        self._mount_path = Path(mount_path)
        self._root = self._mount_path / GARMIN_DIR

    # -- helpers -------------------------------------------------------------

    def _category_dir(self, category: str) -> Path:
        if category not in VALID_CATEGORIES:
            raise ValueError(
                f"Catégorie invalide : {category!r} "
                f"(attendu l'une de {sorted(VALID_CATEGORIES)})"
            )
        return self._root / category

    def _resolve(self, path: Path) -> Path:
        """Résout un chemin relatif à la racine GARMIN/ en chemin absolu."""
        return self._root / path

    # -- API publique --------------------------------------------------------

    def list_fit_files(self, category: str) -> list[Path]:
        """Retourne les fichiers `.FIT` de `GARMIN/{category}/`, triés par nom.

        Chaque chemin est relatif à la racine GARMIN/ (ex. `Workouts/foo.FIT`).
        Retourne `[]` si le dossier n'existe pas. Les sous-dossiers et les
        fichiers d'extension non-FIT sont ignorés.
        """
        directory = self._category_dir(category)
        if not directory.is_dir():
            return []
        files = [
            Path(category) / entry.name
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() == ".fit"
        ]
        return sorted(files)

    def read_fit(self, path: Path) -> bytes:
        """Lit un fichier FIT (chemin relatif à GARMIN/). Lève `OSError` si absent."""
        return self._resolve(path).read_bytes()

    def write_fit(self, path: Path, data: bytes) -> None:
        """Écrit un fichier FIT (chemin relatif à GARMIN/), en créant le dossier parent.

        Lève `OSError` en cas d'échec (déconnexion USB, permissions…).
        """
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
