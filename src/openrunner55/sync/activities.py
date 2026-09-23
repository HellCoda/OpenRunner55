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

**409 Duplicate Activity** (Epic 5, chantier 1) : Garmin Connect répond 409
quand le fichier .FIT a déjà été uploadé. La lib `garminconnect` ne lève pas
d'exception dédiée pour ce cas — `upload_activity` appelle
`Client._run_request` qui raise `GarminConnectConnectionError("API Error 409
- ...")` (cf. `garminconnect/client.py`). On catche donc
`GarminConnectConnectionError` et on matche le message (insensible à la
casse) sur ``"409"`` ou ``"duplicate"`` pour distinguer un vrai doublon d'une
erreur réseau générique. Le 409 est un skip sémantique (GC a confirmé la
présence) : on marque le fichier comme transféré, sans entrée dans `errors`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from garminconnect import GarminConnectConnectionError

from openrunner55.garmin.client import GarminClient
from openrunner55.store.history import SyncHistoryStore
from openrunner55.store.logger import OperationLogger
from openrunner55.store.transfers import TransferredFilesStore
from openrunner55.watch.filesystem import WatchFilesystem

# Catégories de dossiers FIT uploadables vers GC (spike S2). L'ordre définit
# l'ordre de listing : Activity en premier (chronologique, le plus consulté).
UPLOADABLE_CATEGORIES = ("Activity", "Monitor", "Sleep", "Metrics")

# Catégories exclues de l'upload : SUMMARY/ est rejeté (406) par GC.
EXCLUDED_CATEGORIES = ("SUMMARY",)

# Sens de la déduplication : montée Montre → GC.
_DIRECTION = "up"


def _is_duplicate_409(exc: Exception) -> bool:
    """Détecte un 409 Duplicate Activity levé par `garminconnect`.

    La lib ne fournit pas d'exception dédiée pour le 409 (uniquement pour 401,
    429, 404) : `upload_activity` propage un `GarminConnectConnectionError`
    dont le message est formaté ``"API Error 409 - ..."``. On matche donc le
    message insensible à la casse sur ``"409"`` ou ``"duplicate"`` (ce dernier
    couvre le chemin `import_activity` et une éventuelle évolution de la lib).
    """
    if not isinstance(exc, GarminConnectConnectionError):
        return False
    message = str(exc).lower()
    return "409" in message or "duplicate" in message


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


def push_activities(
    client: GarminClient,
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
    history: SyncHistoryStore,
    logger: OperationLogger,
    items: list[UploadableFile],
) -> SyncResult:
    """Upload les fichiers sélectionnés vers Garmin Connect.

    Par fichier : résout le chemin absolu (`watch.absolute_path`) →
    `client.upload_activity(path)` → `transfers.mark_transferred(file_name,
    "up", source)` en cas de succès. En cas d'échec d'un fichier, on continue au
    suivant (l'erreur est collectée dans `SyncResult.errors`). En fin
    d'opération, une entrée est ajoutée à l'historique des syncs.

    Les fichiers `already_transferred=True` sont skipés (aucun appel API — le
    compte `skipped` est reporté dans le `SyncResult`). Le succès est déterminé
    par l'absence d'exception de `upload_activity` (les 4 catégories sont
    validées par le spike S2 ; `detailedImportResult` n'est pas parsé au MVP).

    Un 409 Duplicate Activity de GC est traité comme un skip (le fichier est
    marqué transféré) — cf. `_is_duplicate_409` et la note module.
    """
    total = len(items)
    if total == 0:
        return SyncResult(total=0, success=0, failed=0, errors=[], skipped=0)

    success = 0
    skipped = 0
    errors: list[str] = []
    uploaded_files: list[str] = []

    for item in items:
        if item.already_transferred:
            skipped += 1
            continue
        try:
            absolute = watch.absolute_path(item.path)
            client.upload_activity(absolute)
            transfers.mark_transferred(item.path.name, _DIRECTION, item.category)
            uploaded_files.append(item.path.name)
            success += 1
        except GarminConnectConnectionError as exc:
            # 409 Duplicate Activity : GC a déjà le fichier → skip sémantique.
            if _is_duplicate_409(exc):
                skipped += 1
                transfers.mark_transferred(item.path.name, _DIRECTION, item.category)
                logger.log(
                    "sync.activities",
                    "info",
                    f"Activity déjà présente sur GC : {item.path}",
                )
                continue
            # Autre erreur de connexion GC (5xx, 4xx non-409) → échec réel.
            errors.append(f"file {item.path}: {type(exc).__name__}: {exc}")
            logger.log(
                "sync.activities",
                "error",
                f"Échec upload {item.path}: {exc}",
            )
        except Exception as exc:  # noqa: BLE001 — on continue au suivant (brief)
            errors.append(f"file {item.path}: {type(exc).__name__}: {exc}")
            logger.log(
                "sync.activities",
                "error",
                f"Échec upload {item.path}: {exc}",
            )

    failed = total - success - skipped
    status = "success" if failed == 0 else ("partial" if success > 0 else "failed")
    details = json.dumps(
        {"files": uploaded_files, "errors": errors, "skipped": skipped}
    )
    # Les `errors` peuvent contenir un message d'exception brut : on applique le
    # filtre anti-credentials avant persistance (cohérent avec operation_logs).
    history.log_sync(_DIRECTION, success, status, OperationLogger.redact(details))
    logger.log(
        "sync.activities",
        "ok" if failed == 0 else ("warning" if success > 0 else "error"),
        f"{success}/{total - skipped} fichiers uploadés vers GC ({skipped} skippés)",
    )
    return SyncResult(
        total=total, success=success, failed=failed, errors=errors, skipped=skipped
    )
