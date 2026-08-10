"""Application GTK4 principale (couche UI).

Fenêtre minimale : l'écran d'authentification (auth_view) sera branché au
Bloc 5. Ce module reste volontairement simple — la navigation complète relève
de l'UX Designer (voir docs/conception/ux-design.md).
"""

from __future__ import annotations

import logging
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw

from openrunner55 import __version__

_LOGGER = logging.getLogger(__name__)


class OpenRunnerApp(Adw.Application):
    """Application GTK principale."""

    def __init__(self) -> None:
        super().__init__(application_id="io.github.openrunner55")
        self.connect("activate", self.on_activate)

    def on_activate(self, app: Adw.Application) -> None:
        """Crée la fenêtre principale au démarrage."""
        window = Adw.ApplicationWindow(application=app)
        window.set_title("OpenRunner55")
        window.set_default_size(900, 600)
        window.present()


def main() -> int:
    """Configure les logs puis lance l'application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _LOGGER.info("OpenRunner55 v%s — démarrage", __version__)
    return OpenRunnerApp().run(sys.argv)
