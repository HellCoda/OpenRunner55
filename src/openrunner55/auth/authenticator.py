"""Authentification headless Garmin Connect (auth Core).

Stratégie headless : la bibliothèque garminconnect 0.3.9 enchaîne une cascade
de stratégies HTTP pures (mobile+cffi, widget+cffi, portal+cffi…) sans
navigateur — validée par le spike S-2. Nous passons la main à la lib ; ce
module orchestre : login, persistance de session (tokenstore), reprise et
détection MFA (ADR-004 : MFA non supporté).

Tokenstore : `~/.config/openrunner55/tokens.json` (chmod 600, dossier 700 —
géré par la lib lors du dump). Ne contient que les tokens, jamais le mot de
passe (ADR-004).
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)

from openrunner55.auth.keyring_store import KeyringStore
from openrunner55.store.logger import OperationLogger

_LOGGER = logging.getLogger(__name__)

TOKENSTORE_DIR = Path("~/.config/openrunner55").expanduser()
TOKENSTORE_FILE = TOKENSTORE_DIR / "tokens.json"

MFA_UNSUPPORTED_MESSAGE = (
    "L'authentification multi-facteurs (MFA) n'est pas supportée. "
    "Désactivez-la temporairement dans vos paramètres Garmin Connect pour "
    "utiliser OpenRunner55."
)


class GarminMFAError(Exception):
    """MFA requis par Garmin — non supporté (ADR-004)."""


class GarminLoginError(Exception):
    """Échec d'authentification (credentials invalides, 429, réseau…)."""


class SessionNotFoundError(Exception):
    """Aucune session active : reprise impossible, login requis."""


def _token_expiry(di_token: str | None) -> datetime | None:
    """Extrait l'expiration `exp` du JWT `di_token` (UTC), ou None si indécodable."""
    if not di_token:
        return None
    try:
        parts = str(di_token).split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode()).decode())
        exp = payload.get("exp")
        if exp:
            return datetime.fromtimestamp(int(exp), tz=timezone.utc)
    except Exception:
        return None
    return None


class Authenticator:
    """Orchestration de l'authentification Garmin Connect.

    :param keyring: stockage des credentials (GNOME Keyring, ADR-004)
    :param logger: journalise les opérations (store Core) — optionnel
    """

    def __init__(
        self,
        keyring: KeyringStore | None = None,
        logger: OperationLogger | None = None,
    ) -> None:
        self._keyring = keyring or KeyringStore()
        self._logger = logger

    # -- journalisation -----------------------------------------------------

    def _log(self, operation: str, status: str, message: str) -> None:
        if self._logger is not None:
            self._logger.log(operation, status, message)

    # -- login --------------------------------------------------------------

    def login(self, email: str, password: str) -> Garmin:
        """Connecte à Garmin Connect et retourne le client authentifié.

        Sauvegarde les credentials dans le keyring et le tokenstore sur disque.
        Lève GarminMFAError si MFA requis, GarminLoginError sinon.
        """
        garmin = Garmin(email=email, password=password)
        try:
            mfa_status, _ = garmin.login(str(TOKENSTORE_FILE))
        except GarminConnectTooManyRequestsError as exc:
            self._log("auth.login", "error", f"429 rate limit : {exc}")
            raise GarminLoginError(
                "Garmin a bloqué temporairement les connexions (429). "
                "Patientez quelques minutes puis réessayez."
            ) from exc
        except GarminConnectAuthenticationError as exc:
            self._log("auth.login", "error", "credentials rejetés par Garmin")
            raise GarminLoginError(
                "Identifiants incorrects. Vérifiez votre email et mot de passe."
            ) from exc
        except GarminConnectConnectionError as exc:
            self._log("auth.login", "error", f"erreur de connexion : {exc}")
            raise GarminLoginError(
                "Connexion à Garmin impossible. Vérifiez votre réseau."
            ) from exc

        if mfa_status == "needs_mfa":
            self._log("auth.login", "error", "MFA requis, non supporté")
            raise GarminMFAError(MFA_UNSUPPORTED_MESSAGE)

        # Credentials mémorisés (échec silencieux si keyring indisponible)
        self._keyring.save(email, password)
        self._log("auth.login", "ok", "connexion réussie")
        return garmin

    # -- reprise de session -------------------------------------------------

    def resume_session(self) -> Garmin | None:
        """Reprend une session depuis le tokenstore sans credentials.

        Retourne le client authentifié, ou None si aucun tokenstore valide.
        """
        if not TOKENSTORE_FILE.is_file():
            return None
        try:
            garmin = Garmin()
            mfa_status, _ = garmin.login(str(TOKENSTORE_FILE))
            if mfa_status == "needs_mfa":
                self._log("auth.login", "error", "MFA requis pendant la reprise")
                raise GarminMFAError(MFA_UNSUPPORTED_MESSAGE)
            self._log("auth.session", "ok", "session reprise depuis tokenstore")
            return garmin
        except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
            _LOGGER.debug("Reprise de session impossible : %s", exc)
            self._log("auth.session", "warning", "tokenstore invalide ou expiré")
            return None

    # -- état ---------------------------------------------------------------

    @staticmethod
    def is_authenticated(client: Garmin | None) -> bool:
        """True si le client porte un token non expiré.

        Vérifie l'expiration du JWT `di_token`. Si l'expiration n'est pas
        déterminable mais qu'un token est présent, considère authentifié
        (le token a été validé par la lib au login).
        """
        if client is None:
            return False
        try:
            di_token = client.client.di_token if hasattr(client, "client") else getattr(client, "di_token", None)
        except AttributeError:
            di_token = None
        if not di_token:
            return False
        exp = _token_expiry(di_token)
        if exp is None:
            return True  # token présent, expiration non déterminable
        return exp > datetime.now(timezone.utc)

    def get_client(self) -> Garmin:
        """Retourne un client authentifié : reprend la session si possible.

        Lève SessionNotFoundError si aucune session ne peut être reprise —
        l'appelant doit alors demander un login à l'utilisateur.
        """
        client = self.resume_session()
        if client is None:
            raise SessionNotFoundError(
                "Aucune session active. Veuillez vous connecter."
            )
        return client

    # -- gestion des credentials --------------------------------------------

    def save_credentials(self, email: str, password: str) -> bool:
        """Délègue au keyring (ADR-004). Retourne False si keyring indisponible."""
        return self._keyring.save(email, password)

    def get_email(self) -> str | None:
        """Retourne l'email stocké dans le keyring, ou None si indisponible."""
        creds = self._keyring.load()
        return creds[0] if creds else None

    def delete_credentials(self) -> bool:
        """Supprime credentials (keyring) et tokenstore. Retourne True si nettoyé."""
        removed = self._keyring.delete()
        if TOKENSTORE_FILE.is_file():
            TOKENSTORE_FILE.unlink()
            removed = True
        self._log("auth.session", "warning", "déconnexion : credentials et session effacés")
        return removed
