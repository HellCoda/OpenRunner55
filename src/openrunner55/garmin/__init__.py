"""Garmin Core — wrapper client API Garmin Connect.

Co-localisé avec auth/ dans la couche Core (ADR-002) : la bibliothèque
garminconnect fusionne auth et client API dans un même objet Garmin().

Ce module applique la stratégie réseau d'ADR-007 :
- délai inter-requêtes préventif (3 s, évite le 429)
- backoff exponentiel sur 429 (1-2-4 s, max 3 retries) — la lib fait fail-fast
  sur 429, le retry est notre responsabilité
- re-login automatique sur 401 via auth/ (session expirée)
Le retry 5xx/réseau est déjà géré en interne par la lib (retry_attempts=3) —
pas de double gestion.
"""

from openrunner55.garmin.client import GarminClient, GarminAuthError

__all__ = ["GarminClient", "GarminAuthError"]
