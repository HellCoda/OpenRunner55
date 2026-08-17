"""Service de synchronisation Cloud → Montre des workouts (sync) — ADR-002.

Cœur métier de l'Epic 2 : récupère la liste des workouts Garmin Connect, les
télécharge en `.FIT`, applique le slugify (nommage FAT32 lisible) avec gestion
des collisions, copie sur la montre et trace en base (transferts + historique).

Le slugify est ici (Service), pas dans `watch/` (Core) : `watch/filesystem.py`
reçoit un chemin final et écrit des bytes, sans logique de nommage (ADR-002).
Le nom affiché par la montre vient du champ `wkt_name` dans le FIT, pas du nom
de fichier — le slug ne sert qu'à la lisibilité du système de fichiers FAT32.

`push_workouts` reçoit `items: list[WorkoutSummary]` (id + nom fournis par le
frontend, qui a déjà appelé `fetch_workouts` pour afficher la liste) — aucun
appel `get_workouts()` supplémentaire. Si le nom est vide, repli sur
`workout_{id}` comme slug.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from openrunner55.garmin.client import GarminClient
from openrunner55.store.history import SyncHistoryStore
from openrunner55.store.logger import OperationLogger
from openrunner55.store.transfers import TransferredFilesStore
from openrunner55.watch.filesystem import WatchFilesystem

MAX_SLUG_LENGTH = 40

# Ordre de priorité des champs date de la réponse GC (le plus « récent » d'abord).
_DATE_FIELDS = ("updatedDate", "createdDate")

_WORKOUTS_CATEGORY = "Workouts"


@dataclass
class WorkoutSummary:
    """Un workout listable par l'UI (trié du plus récent au plus ancien)."""

    workout_id: int
    name: str
    date: datetime | None  # None si absente/non parsable → le tri conserve l'ordre API
    type: str  # sport / catégorie (ex. "running")


@dataclass
class SyncResult:
    """Bilan d'une opération `push_workouts`."""

    total: int
    success: int
    failed: int
    errors: list[str]  # un message par workout échoué


def slugify(name: str) -> str:
    """Normalise un nom de workout en nom de fichier FAT32 lisible (ADR-002).

    Règles :
    - minuscules ;
    - suppression des accents (normalisation NFKD + suppression des diacritiques) ;
    - espaces → `_` (séquences d'espaces repliées sur un seul `_`) ;
    - suppression des caractères non alphanumériques (sauf `_`) ;
    - suppression des `_` de début/fin (résidus d'espaces ou de ponctuation) ;
    - longueur max `MAX_SLUG_LENGTH` (40) caractères ;
    - résultat vide → `"workout"`.
    """
    normalized = unicodedata.normalize("NFKD", name)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_text.lower()
    underscored = re.sub(r"\s+", "_", lowered)
    cleaned = re.sub(r"[^a-z0-9_]+", "", underscored)
    slug = cleaned.strip("_")
    return slug[:MAX_SLUG_LENGTH] or "workout"


def _parse_date(value: object) -> datetime | None:
    """Parse une date ISO de la réponse GC ; None si absente ou non parsable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_type(workout: dict) -> str:
    """Extrait le type de sport (ex. "running") depuis `sportType.sportTypeKey`."""
    sport = workout.get("sportType")
    if isinstance(sport, dict):
        key = sport.get("sportTypeKey")
        if isinstance(key, str) and key:
            return key
    return "unknown"


def _to_summary(workout: dict) -> WorkoutSummary:
    date: datetime | None = None
    for field in _DATE_FIELDS:
        date = _parse_date(workout.get(field))
        if date is not None:
            break
    return WorkoutSummary(
        workout_id=int(workout.get("workoutId", 0)),
        name=str(workout.get("workoutName") or ""),
        date=date,
        type=_extract_type(workout),
    )


def fetch_workouts(client: GarminClient) -> list[WorkoutSummary]:
    """Récupère et trie les workouts GC, du plus récent au plus ancien.

    Les workouts sans date (ou date non parsable) sont placés en fin de liste en
    conservant leur ordre relatif d'API (tri stable).
    """
    raw = client.get_workouts()
    summaries = [_to_summary(workout) for workout in raw]
    summaries.sort(key=lambda s: s.date or datetime.min, reverse=True)
    return summaries


def _unique_slug(base: str, existing: set[str]) -> str:
    """Retourne un slug sans collision : suffixe `_2`, `_3`… (≤ 40 car. avant `.FIT`).

    `existing` contient les noms de fichiers déjà présents, en minuscules
    (FAT32 est insensible à la casse).
    """
    candidate = base
    counter = 2
    while f"{candidate}.fit" in existing:
        suffix = f"_{counter}"
        candidate = base[: MAX_SLUG_LENGTH - len(suffix)] + suffix
        counter += 1
    return candidate


def push_workouts(
    client: GarminClient,
    watch: WatchFilesystem,
    transfers: TransferredFilesStore,
    history: SyncHistoryStore,
    logger: OperationLogger,
    items: list[WorkoutSummary],
) -> SyncResult:
    """Télécharge, slugify, copie sur la montre, trace en base (flux Epic 2).

    Par workout sélectionné : download `.FIT` → slugify(nom) → gestion des
    collisions → `watch.write_fit(Workouts/{slug}.FIT)` → marquage transféré.
    En cas d'échec d'un workout, on continue au suivant (l'erreur est collectée).
    En fin d'opération, une entrée est ajoutée à l'historique des syncs.

    Les noms proviennent des `items` (le frontend les a via `fetch_workouts`) :
    pas d'appel API redondant, pas de piège de pagination.
    """
    total = len(items)
    if total == 0:
        return SyncResult(total=0, success=0, failed=0, errors=[])

    existing = {p.name.lower() for p in watch.list_fit_files(_WORKOUTS_CATEGORY)}

    success = 0
    errors: list[str] = []
    pushed_files: list[str] = []

    for item in items:
        try:
            fit_bytes = client.download_workout(item.workout_id)
            base = slugify(item.name) if item.name else f"workout_{item.workout_id}"
            slug = _unique_slug(base, existing)
            filename = f"{slug}.FIT"
            watch.write_fit(Path(_WORKOUTS_CATEGORY) / filename, fit_bytes)
            transfers.mark_transferred(filename, "down", "workout")
            existing.add(filename.lower())
            pushed_files.append(filename)
            success += 1
        except Exception as exc:  # noqa: BLE001 — on continue au suivant (brief)
            errors.append(
                f"workout {item.workout_id}: {type(exc).__name__}: {exc}"
            )
            logger.log(
                "sync.workouts",
                "error",
                f"Échec workout {item.workout_id}: {exc}",
            )

    failed = total - success
    status = "success" if failed == 0 else ("partial" if success > 0 else "failed")
    details = json.dumps({"files": pushed_files, "errors": errors})
    # Les `errors` peuvent contenir un message d'exception brut : on applique le
    # filtre anti-credentials avant persistance (cohérent avec operation_logs).
    history.log_sync("down", success, status, OperationLogger.redact(details))
    logger.log(
        "sync.workouts",
        "ok" if failed == 0 else ("warning" if success > 0 else "error"),
        f"{success}/{total} workouts poussés vers la montre",
    )
    return SyncResult(total=total, success=success, failed=failed, errors=errors)
