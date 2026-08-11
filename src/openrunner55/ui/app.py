"""Application GTK4 principale (couche UI).

Au démarrage, tente une reprise de session (`resume_session`) dans un thread
— l'UI ne doit jamais geler sur un appel réseau (ADR-007). Selon le résultat :
- session reprise → vue principale (placeholder pour l'instant, les vues
  métier arrivent aux Epics 2-4)
- sinon → écran de login (`auth_view`), qui émet `authenticated` avec le
  client à la connexion.

La navigation complète (account_view, watch_view, history_view) relève de
l'UX Designer (voir docs/conception/ux-design.md) — ce module reste minimal.
"""

from __future__ import annotations

import logging
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from openrunner55 import __version__
from openrunner55.auth.authenticator import Authenticator
from openrunner55.ui.auth_view import AuthView

_LOGGER = logging.getLogger(__name__)


class OpenRunnerApp(Adw.Application):
    """Application GTK principale."""

    def __init__(self) -> None:
        super().__init__(application_id="io.github.openrunner55")
        self.connect("activate", self.on_activate)
        self._window: Adw.ApplicationWindow | None = None
        self._authenticator = Authenticator()

    def on_activate(self, app: Adw.Application) -> None:
        """Prépare la fenêtre puis lance la reprise de session en arrière-plan."""
        self._window = Adw.ApplicationWindow(application=app)
        self._window.set_title("OpenRunner55")
        self._window.set_default_size(900, 600)

        # Écran de secours immédiat : rien n'est bloquant, la reprise de session
        # remplacera le contenu si elle réussit.
        self._window.set_content(self._build_placeholder("Connexion en cours…"))
        self._window.present()

        thread = threading.Thread(target=self._restore_session_worker, daemon=True)
        thread.start()

    # -- session -------------------------------------------------------------

    def _restore_session_worker(self) -> None:
        """Tente une reprise de session hors du thread GTK."""
        try:
            client = self._authenticator.resume_session()
        except Exception:
            _LOGGER.exception("Erreur pendant la reprise de session")
            client = None
        GLib.idle_add(self._on_session_restored, client)

    def _on_session_restored(self, client) -> None:
        if self._window is None:
            return
        if client is not None:
            self._show_main_view()
        else:
            self._show_login_view()

    # -- vues ----------------------------------------------------------------

    def _show_login_view(self) -> None:
        if self._window is None:
            return
        view = AuthView(authenticator=self._authenticator)
        view.connect("authenticated", self._on_authenticated)
        self._window.set_content(view)

    def _on_authenticated(self, _view, client) -> None:
        _LOGGER.info("Authentification réussie")
        self._show_main_view()

    def _show_main_view(self) -> None:
        """Vue principale : placeholder en attendant les Epics 2-4."""
        if self._window is None:
            return
        self._window.set_content(self._build_placeholder("Connecté — vues métier à venir"))

    @staticmethod
    def _build_placeholder(text: str) -> Gtk.Widget:
        label = Gtk.Label(label=text)
        label.set_margin_top(48)
        return label


def main() -> int:
    """Configure les logs puis lance l'application."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    _LOGGER.info("OpenRunner55 v%s — démarrage", __version__)
    return OpenRunnerApp().run(sys.argv)
