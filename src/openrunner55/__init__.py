"""OpenRunner55 — synchronisation bidirectionnelle Garmin Connect / FR55.

Architecture 3 couches : UI → Services → Core (voir docs/decisions/adr-002.md).
Ce package expose le noyau métier (auth, garmin, store) et l'interface GTK4.
"""

__version__ = "0.1.0"
