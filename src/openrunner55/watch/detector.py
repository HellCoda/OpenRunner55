"""Détection USB de la montre FR55 (watch Core) — ADR-006.

Deux chemins de détection complémentaires, un seul état interne :

1. **pyudev (actif)** : `pyudev.Monitor` sur le sous-système `block`, à l'écoute
   des événements `bind`/`unbind`. Quand un device dont le label de volume est
   `GARMIN` est signalé, on re-vérifie immédiatement la présence du fichier de
   confirmation `GARMIN/GarminDevice.xml` (identification FR55).
2. **Polling (fallback)** : toutes les `poll_interval` secondes, on vérifie si
   `/run/media/$USER/GARMIN/GARMIN/GarminDevice.xml` existe. Filet de sécurité
   si pyudev manque un événement (permissions, conteneur, session non systemd)
   — ou si pyudev est tout simplement absent (l'import est optionnel).

Le monitor et le polling tournent dans **un seul thread dédié** (daemon) pour
ne pas bloquer la boucle principale GTK. Le signal `on_status_changed` est émis
thread-safe : si GLib est disponible, le callback est marshallé vers la boucle
GTK via `GLib.idle_add` (ADR-006) ; sinon (tests, CLI sans GTK) il est invoqué
directement dans le thread du détecteur.

Le point de montage est déterministe : GNOME (gvfs/udisks) monte les volumes
par label, d'où `/run/media/$USER/GARMIN`. La confirmation FR55 est le fichier
`GARMIN/GarminDevice.xml` au sein du volume (cf. `docs/exploration/tree-FR55.md`).

Le détecteur est testable sans montre branchée : le point de montage racine
(`mount_root`) est injectable au constructeur, et pyudev est mocké (ou absent).
"""

from __future__ import annotations

import getpass
import logging
import threading
from pathlib import Path
from typing import Callable

_LOGGER = logging.getLogger(__name__)

# Import optionnel de pyudev (ADR-006) : le polling prend le relais si absent.
# `pyudev` est déclaré dans pyproject.toml, mais le fallback garde le module
# importable (et testable) dans un environnement où il manquerait.
try:
    import pyudev as _pyudev
except ImportError:  # pragma: no cover - dépend de l'environnement
    _pyudev = None

# Import optionnel de GLib : nécessaire pour marshaller le signal vers la
# boucle GTK. Le watcher reste importable sans PyGObject (tests, CLI).
try:
    from gi.repository import GLib as _GLib  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - dépend de l'environnement
    _GLib = None

# Label FAT32 du volume FR55 (nom du point de montage GNOME).
VOLUME_LABEL = "GARMIN"

# Chemin relatif de confirmation de la FR55, au sein du volume monté :
#   /run/media/$USER/GARMIN  /  GARMIN  /  GarminDevice.xml
CONFIRMATION_REL = Path("GARMIN") / "GarminDevice.xml"


def default_mount_root() -> Path:
    """Racine des points de montage de l'utilisateur courant (GNOME/gvfs)."""
    return Path("/run/media") / getpass.getuser()


def _emit_thread_safe(callback: Callable[[bool], None], connected: bool) -> None:
    """Émet le signal `on_status_changed` de façon thread-safe (ADR-006).

    Si GLib est disponible, le callback est différé sur la boucle principale
    GTK via `GLib.idle_add` (le thread du détecteur n'y touche jamais
    directement). Sinon, invocation directe (tests, environnement sans GTK).
    """
    if _GLib is not None:
        _GLib.idle_add(callback, connected)
    else:
        callback(connected)


class WatchDetector:
    """Détecte la connexion/déconnexion USB de la montre FR55.

    :param mount_root: racine des points de montage (défaut `/run/media/$USER`).
        Injectable pour les tests (pointer vers un `tmp_path`).
    :param poll_interval: période de polling du fallback, en secondes (défaut 1 s).
    """

    def __init__(
        self,
        mount_root: Path | None = None,
        poll_interval: float = 1.0,
    ) -> None:
        self._mount_root = mount_root or default_mount_root()
        self._poll_interval = poll_interval
        self._callbacks: list[Callable[[bool], None]] = []
        self._lock = threading.Lock()
        self._connected = False
        self._mount_path: Path | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # -- état (contrat frontend) ---------------------------------------------

    def is_connected(self) -> bool:
        """Retourne True si une FR55 est actuellement détectée comme branchée."""
        with self._lock:
            return self._connected

    def get_mount_path(self) -> Path | None:
        """Point de montage du volume FR55 (`.../GARMIN`), ou None si déconnecté."""
        with self._lock:
            return self._mount_path if self._connected else None

    def on_status_changed(self, callback: Callable[[bool], None]) -> None:
        """Enregistre un callback appelé à chaque changement d'état (True/False).

        Le callback est invoqué thread-safe (voir `_emit_thread_safe`). Les
        callbacks reçoivent le nouvel état `connected`.
        """
        with self._lock:
            self._callbacks.append(callback)

    # -- cycle de vie --------------------------------------------------------

    def start(self) -> None:
        """Démarre le thread de détection (monitor pyudev + polling).

        Idempotent : ne redémarre pas si un thread tourne déjà. À appeler après
        l'authentification (côté frontend).
        """
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="WatchDetector", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Signale l'arrêt du thread et attend sa fin (borné à ~2 s)."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    # -- internes ------------------------------------------------------------

    def _confirmation_path(self) -> Path:
        """Chemin du fichier de confirmation FR55 à surveiller."""
        return self._mount_root / VOLUME_LABEL / CONFIRMATION_REL

    def _check_state(self) -> bool:
        """Re-évalue l'état de connexion ; émet le signal si l'état a changé.

        :returns: le nouvel état `connected`.
        """
        connected = self._confirmation_path().is_file()
        with self._lock:
            changed = connected != self._connected
            self._connected = connected
            self._mount_path = (
                self._mount_root / VOLUME_LABEL if connected else None
            )
            callbacks = list(self._callbacks) if changed else []
        if changed:
            _LOGGER.info(
                "Montre %s", "connectée" if connected else "déconnectée"
            )
            for callback in callbacks:
                _emit_thread_safe(callback, connected)
        return connected

    @staticmethod
    def _is_garmin_device(device) -> bool:
        """True si l'événement udev concerne un device au label `GARMIN`."""
        return device.get("ID_FS_LABEL") == VOLUME_LABEL

    def _start_monitor(self):
        """Démarre le monitor pyudev, ou retourne None en cas d'indisponibilité."""
        if _pyudev is None:
            _LOGGER.warning(
                "pyudev indisponible — repli sur le polling seul (ADR-006)"
            )
            return None
        try:
            context = _pyudev.Context()
            monitor = _pyudev.Monitor.from_netlink(context)
            monitor.filter_by(subsystem="block")
            monitor.start()
            return monitor
        except Exception as exc:  # pragma: no cover - dépend de l'environnement udev
            _LOGGER.warning(
                "Échec du démarrage du monitor pyudev (%s) — repli polling", exc
            )
            return None

    def _run(self) -> None:
        """Boucle du thread : état initial puis monitor pyudev + polling entrelacés.

        `monitor.poll(timeout=poll_interval)` retourne un Device sur événement,
        ou None sur timeout. Le timeout sert de tick au polling fallback ; un
        événement au label `GARMIN` déclenche une re-vérification immédiate
        (détection plus rapide que la seconde du polling).
        """
        self._check_state()
        monitor = self._start_monitor()
        while not self._stop_event.is_set():
            if monitor is None:
                # pyudev indisponible : polling seul
                self._stop_event.wait(self._poll_interval)
            else:
                device = monitor.poll(timeout=self._poll_interval)
                if device is not None and not self._is_garmin_device(device):
                    # événement block sans rapport : on l'ignore (le timeout
                    # continue d'assurer le polling toutes les poll_interval)
                    continue
            self._check_state()
