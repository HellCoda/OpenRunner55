"""Auth Core — authentification Garmin Connect.

Co-localisé avec garmin/ dans la couche Core (ADR-002) : la bibliothèque
garminconnect fusionne auth + client API dans un même objet Garmin().
"""

from openrunner55.auth.authenticator import (
    Authenticator,
    GarminLoginError,
    GarminMFAError,
)
from openrunner55.auth.keyring_store import KeyringStore

__all__ = ["Authenticator", "GarminLoginError", "GarminMFAError", "KeyringStore"]
