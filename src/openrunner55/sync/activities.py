"""Service de synchronisation Montre → Garmin Connect (sync) — ADR-002.

Cœur métier de l'Epic 3 : liste les fichiers .FIT natifs de la montre
(`Activity/`, `Monitor/`, `Sleep/`, `Metrics/`) et les téléverse vers Garmin
Connect via `GarminClient.upload_activity`.

**Classification par dossier** (pas de décodage FIT au MVP — `fit/decoder.py`
ajourné, cf. ADR-002) : les dossiers natifs sont uploadables, `SUMMARY/` est
exclu (rejeté 406 par GC, cf. `spike-S2-resultat.md`). La déduplication locale
(`transferred_files`) évite de re-uploader un fichier déjà envoyé (délai
inter-requêtes 3 s — ADR-007).

`list_uploadable_files` retourne des `UploadableFile` (chemin relatif à
`GARMIN/`), que le frontend affiche ; `push_activities` reçoit ensuite ces
mêmes objets sélectionnés (pas de re-listing).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openrunner55.store.transfers import TransferredFilesStore
from openrunner55.watch.filesystem import WatchFilesystem

# Catégories de dossiers FIT uploadables vers GC (spike S2). L'ordre définit
# l'ordre de listing : Activity en premier (chronologique, le plus consulté).
UPLOADABLE_CATEGORIES = ("Activity", "Monitor", "Sleep", "Metrics")

# Catégories exclues de l'upload : SUMMARY/ est rejeté (406) par GC.
EXCLUDED_CATEGORIES = ("SUMMARY",)

# Sens de la déduplication : montée Montre → GC.
_DIRECTION = "up"


@dataclass
class UploadableFile:
    """Un fichier .FIT sur la montre, candidat à l'upload vers GC."""

    path: Path  # chemin relatif à GARMIN/ (ex. "Activity/2026-08-07-08-29-33.fit")
    category: str  # "activity" | "monitor" | "sleep" | "metrics"
    size: int  # taille en octets
    already_transferred: bool  # True si déjà uploadé (dédup locale)


@dataclass
class SyncResult:
    """Bilan d'une opération `push_activities` (réutilise le pattern de l'Epic 2)."""

    total: int
    success: int
    failed: int
    errors: list[str]  # un message par fichier échoué
    skipped: int  # fichiers ignorés (déjà transférés)


def list_uploadable_files(
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
) -> list[UploadableFile]:
    """Liste les fichiers .FIT uploadables sur la montre, avec statut de dédup.

    Parcourt les dossiers `UPLOADABLE_CATEGORIES` via
    `watch.list_fit_files(category)`, détermine la taille via
    `watch.file_size(path)` et le statut `already_transferred` via
    `transfers.is_transferred(file_name, "up", source)`.

    Tri : par catégorie (ordre de `UPLOADABLE_CATEGORIES`) puis par nom de
    fichier (tri délégué à `list_fit_files` ; chronologique pour Activity/ dont
    les noms sont des timestamps).
    """
    result: list[UploadableFile] = []
    for folder in UPLOADABLE_CATEGORIES:
        source = folder.lower()
        for path in watch.list_fit_files(folder):
            result.append(
                UploadableFile(
                    path=path,
                    category=source,
                    size=watch.file_size(path),
                    already_transferred=transfers.is_transferred(
                        path.name, _DIRECTION, source
                    ),
                )
            )
    return result
