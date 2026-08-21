"""Wrapper robuste autour de `garminconnect.Garmin` (garmin Core).

Applique ADR-007 :

- **Délai inter-requêtes** : minimum `INTER_REQUEST_DELAY` (3 s) entre deux
  appels API depuis le même processus. Préventif : vise à ne pas déclencher
  le 429, par opposition au backoff qui est réactif.
- **Backoff exponentiel sur 429** : 1-2-4 s, `MAX_RETRIES` (3) tentatives.
  La bibliothèque garminconnect fait fail-fast sur 429 — le retry est donc
  notre responsabilité.
- **Re-login sur 401** : un 401 signifie token expiré. Le wrapper demande un
  client frais à l'authenticator (`resume_session`), puis retente l'appel une
  fois. Si la reprise échoue, `GarminAuthError` est levée (session expirée).

Le retry 5xx / erreurs réseau est déjà géré en interne par la lib
(`retry_attempts=3`, backoff avec jitter) — pas de double gestion.

Méthodes exposées : `get_workouts`, `get_activities` (Epic 1),
`download_workout` (Epic 2) et `upload_activity` (Epic 3).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

from openrunner55.auth.authenticator import Authenticator, SessionNotFoundError

_LOGGER = logging.getLogger(__name__)


class GarminAuthError(Exception):
    """Session expirée et reprise impossible — l'utilisateur doit se reconnecter."""


class GarminClient:
    """Wrapper de `Garmin()` avec rate-limiting, retry 429 et re-login 401.

    :param authenticator: fournit un client frais pour la cascade 401 (ADR-007)
    :param garmin: objet Garmin() authentifié. Si None, récupéré via
        `authenticator.get_client()`. Injectable pour les tests.
    """

    INTER_REQUEST_DELAY = 3.0  # secondes, préventif (ADR-007)
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # secondes, ×2 à chaque retry (1-2-4)

    def __init__(self, authenticator: Authenticator, garmin=None) -> None:
        self._authenticator = authenticator
        self._garmin = garmin if garmin is not None else authenticator.get_client()
        # Jamais d'attente au premier appel : le délai est écoulé dès le départ.
        self._last_request_time = -float("inf")

    # -- délai inter-requêtes ------------------------------------------------

    def _wait_inter_request(self) -> None:
        """Attend le délai minimum entre deux appels API (ADR-007)."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self.INTER_REQUEST_DELAY:
            time.sleep(self.INTER_REQUEST_DELAY - elapsed)
        self._last_request_time = time.monotonic()

    # -- coeur d'appel -------------------------------------------------------

    def _invoke(self, method_name: str, *args, **kwargs):
        """Délai inter-requêtes puis appel avec retry exponentiel sur 429."""
        self._wait_inter_request()
        last_exc: GarminConnectTooManyRequestsError | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                method = getattr(self._garmin, method_name)
                return method(*args, **kwargs)
            except GarminConnectTooManyRequestsError as exc:
                last_exc = exc
                if attempt == self.MAX_RETRIES:
                    _LOGGER.warning("429 persistant sur %s — abandon", method_name)
                    break
                delay = self.RETRY_BASE_DELAY * (2**attempt)
                _LOGGER.warning(
                    "429 sur %s (essai %d/%d) — backoff %.0fs",
                    method_name,
                    attempt + 1,
                    self.MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    def _call(self, method_name: str, *args, **kwargs):
        """Appel API avec re-login automatique sur 401 (cascade ADR-007)."""
        try:
            return self._invoke(method_name, *args, **kwargs)
        except GarminConnectAuthenticationError:
            _LOGGER.warning("401 sur %s — tentative de reprise de session", method_name)
            try:
                self._garmin = self._authenticator.get_client()
            except SessionNotFoundError as exc:
                _LOGGER.error("Session expirée, reprise impossible")
                raise GarminAuthError(
                    "Session expirée, veuillez vérifier vos identifiants."
                ) from exc
            return self._invoke(method_name, *args, **kwargs)

    # -- API publique ----------------------------------------------------------

    def get_workouts(self, start: int = 0, limit: int = 20) -> list[dict]:
        """Retourne la liste des workouts Garmin (liste de dicts)."""
        return self._call("get_workouts", start, limit)

    def get_activities(self, start: int = 0, limit: int = 20) -> list[dict] | dict:
        """Retourne la liste des activités Garmin."""
        return self._call("get_activities", start, limit)

    def download_workout(self, workout_id: int) -> bytes:
        """Télécharge un workout au format .FIT (bytes) — Epic 2.

        Hérite du délai inter-requêtes, du retry 429 et du re-login 401 via
        `_call()` (ADR-007). Référence : `spike-S2/bloc5_roundtrip_workout.py`
        (`garmin.download_workout(workoutId)` retourne les bytes du FIT).
        """
        return self._call("download_workout", workout_id)

    def upload_activity(self, file_path: str | Path) -> dict:
        """Téléverse un fichier .FIT vers Garmin Connect — Epic 3.

        Hérite du délai inter-requêtes, du retry 429 et du re-login 401 via
        `_call()` (ADR-007). Référence : `spike-S2/bloc3_upload_activity.py`
        (`garmin.upload_activity(path)` retourne un dict avec
        `detailedImportResult`).

        La lib n'accepte qu'un chemin `str` (pas de bytes, pas de `Path`) : le
        wrapper coerce `file_path` en `str` avant l'appel.

        :param file_path: chemin absolu du fichier .FIT à uploader.
        :returns: réponse API GC (dict). Contient `detailedImportResult` avec
            `successes` et `failures`.
        :raises GarminConnectTooManyRequestsError: si 429 persistant après retries.
        :raises GarminAuthError: si session expirée et reprise impossible.
        """
        return self._call("upload_activity", str(file_path))
