"""Application GTK4 principale (couche UI).

Au démarrage, tente une reprise de session (`resume_session`) dans un thread
— l'UI ne doit jamais geler sur un appel réseau (ADR-007). Selon le résultat :
- session reprise → shell principal post-auth (navigation + section Activité)
- sinon → écran de login (`auth_view`), qui émet `authenticated` avec le
  client à la connexion.

Le shell principal post-auth (Epic 2) :
- `Adw.NavigationSplitView` : navigation latérale 3 sections (Activité, Logs &
  Historique, Compte & Paramètres). Activité est la section par défaut ; les
  deux autres sont des placeholders « À venir ».
- `Adw.HeaderBar` avec indicateur de connexion montre (puce verte/grise), mis à
  jour via `WatchDetector.on_status_changed`.
- `WatchDetector.start()` post-auth, `stop()` à la fermeture de la fenêtre.

Composition root : ce module est le point d'entrée qui câble le graphe d'objets
(ADR-002). Il importe donc les modules Core (`garmin/`, `watch/`, `store/`)
**uniquement pour la construction/wiring des dépendances**, jamais pour de la
logique métier. Les vues (`watch_view`) et le controller (`workouts_controller`)
n'importent pas le Core : ils reçoivent les dépendances injectées et délèguent
toute logique métier aux Services (`sync/`).
"""

from __future__ import annotations

import logging
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, GLib, Gtk

from openrunner55 import __version__
from openrunner55.auth.authenticator import Authenticator
from openrunner55.garmin.client import GarminClient
from openrunner55.store.database import Database
from openrunner55.store.history import SyncHistoryStore
from openrunner55.store.logger import OperationLogger
from openrunner55.store.transfers import TransferredFilesStore
from openrunner55.sync.history import HistoryService
from openrunner55.ui.activities_controller import ActivitiesController
from openrunner55.ui.auth_view import AuthView
from openrunner55.ui.history_controller import HistoryController
from openrunner55.ui.history_view import HistoryView
from openrunner55.ui.watch_view import WatchView
from openrunner55.ui.workouts_controller import WorkoutsController
from openrunner55.watch.detector import WatchDetector
from openrunner55.watch.filesystem import WatchFilesystem

_LOGGER = logging.getLogger(__name__)

# Noms des sections (ordre identique à celui des lignes de la navigation).
_SECTION_NAMES = ("activity", "logs", "account")

# CSS applicatif (bleu Garmin #1976d2) :
# - bouton « Envoyer » (suggested-action) ;
# - fond des checkboxes cochées ;
# - arrondi du coin haut-droit de la barre latérale (`sidebar-pane`) ;
# - barre bleue pleine largeur entre l'en-tête et la navigation.
#
# Note : le contournement par variable `--accent-bg-color` ne fonctionne pas
# (l'accent est piloté par `Adw.StyleManager` via le réglage système
# `accent-color`). On cible donc directement les widgets concernés.
_CUSTOM_CSS = """
button.suggested-action {
  background-color: #1976d2;
  color: #ffffff;
}
check:checked, check:indeterminate, radio:checked, radio:indeterminate {
  background-color: #1976d2;
  color: #ffffff;
}
.sidebar-pane {
  border-top-right-radius: 12px;
}
.garmin-bar {
  background-color: #1976d2;
  color: #ffffff;
  padding: 8px 14px;
}
"""


class OpenRunnerApp(Adw.Application):
    """Application GTK principale."""

    def __init__(self) -> None:
        super().__init__(application_id="io.github.openrunner55")
        self.connect("activate", self.on_activate)
        self._window: Adw.ApplicationWindow | None = None
        self._authenticator = Authenticator()
        self._detector: WatchDetector | None = None
        self._history_controller: HistoryController | None = None

    @staticmethod
    def _load_custom_css() -> None:
        """Charge le CSS applicatif (arrondi du coin haut-droit de la sidebar)."""
        provider = Gtk.CssProvider()
        provider.load_from_string(_CUSTOM_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def on_activate(self, app: Adw.Application) -> None:
        """Prépare la fenêtre puis lance la reprise de session en arrière-plan."""
        self._load_custom_css()
        self._window = Adw.ApplicationWindow(application=app)
        self._window.set_title("OpenRunner55")
        self._window.set_default_size(1200, 750)
        self._window.connect("close-request", self._on_close_request)

        # Écran de secours immédiat : rien n'est bloquant, la reprise de session
        # remplacera le contenu si elle réussit.
        self._window.set_content(self._build_placeholder("Connexion en cours…"))
        self._window.present()

        thread = threading.Thread(target=self._restore_session_worker, daemon=True)
        thread.start()

    def _on_close_request(self, _window: Adw.ApplicationWindow) -> bool:
        """Arrête le détecteur USB avant la fermeture (cycle de vie, ADR-006)."""
        if self._detector is not None:
            self._detector.stop()
        return False  # False = autorise la fermeture par défaut

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
            self._show_main_view(client)
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
        self._show_main_view(client)

    def _show_main_view(self, client) -> None:
        """Construit le shell post-auth (navigation + Activité) et le câble."""
        if self._window is None:
            return

        # -- composition root : construction des dépendances Core -------------
        garmin_client = GarminClient(self._authenticator, client)
        db = Database()
        db.connect()
        transfers = TransferredFilesStore(db)
        history = SyncHistoryStore(db)
        logger = OperationLogger(db)

        detector = WatchDetector()
        detector.on_status_changed(self._on_watch_status_changed)
        detector.start()
        self._detector = detector

        def watch_factory(mount_path):
            return WatchFilesystem(mount_path)

        controller = WorkoutsController(
            client=garmin_client,
            watch_factory=watch_factory,
            transfers=transfers,
            history=history,
            logger=logger,
            detector=detector,
            scheduler=GLib.idle_add,
        )

        # Zone Montre (Epic 3) — même graphe de dépendances, même detector
        # partagé (les deux controllers s'abonnent indépendamment au signal).
        activities_controller = ActivitiesController(
            client=garmin_client,
            watch_factory=watch_factory,
            transfers=transfers,
            history=history,
            logger=logger,
            detector=detector,
            scheduler=GLib.idle_add,
        )

        watch_view = WatchView(controller, activities_controller)

        # Section Logs & Historique (Epic 4) — consultation via le Service
        # `sync/history.py` (jamais `store/` directement), conformément à
        # ADR-002. Le chargement initial est déclenché après construction.
        history_service = HistoryService(history, logger)
        history_controller = HistoryController(history_service)
        self._history_controller = history_controller
        history_view = HistoryView(history_controller)
        history_controller.refresh()

        # -- shell ------------------------------------------------------------
        self._content_stack = Gtk.Stack()
        self._content_stack.add_named(watch_view, "activity")
        self._content_stack.add_named(history_view, "logs")
        self._content_stack.add_named(
            self._build_section_placeholder("Compte & Paramètres"), "account"
        )

        sidebar = Gtk.ListBox()
        sidebar.add_css_class("navigation-sidebar")
        sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        sidebar.set_size_request(200, -1)
        self._activity_row = self._build_nav_row("Activité")
        self._logs_row = self._build_nav_row("Logs & Historique")
        self._account_row = self._build_nav_row("Compte & Paramètres")
        for row in (self._activity_row, self._logs_row, self._account_row):
            sidebar.append(row)
        sidebar.connect("row-selected", self._on_nav_selected)

        split = Adw.NavigationSplitView()
        split.set_sidebar(Adw.NavigationPage.new(sidebar, "Navigation"))
        split.set_content(Adw.NavigationPage.new(self._content_stack, "Contenu"))
        split.set_min_sidebar_width(180)
        split.set_max_sidebar_width(260)
        split.set_hexpand(True)
        split.set_vexpand(True)

        header = Adw.HeaderBar()

        # Barre bleue pleine largeur (indicateur montre + emplacement réservé
        # au bouton « ↻ Synchroniser » de l'Epic 3), entre l'en-tête et la
        # navigation.
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_hexpand(True)
        content.set_vexpand(True)
        content.append(self._build_garmin_bar())
        content.append(split)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)

        self._window.set_content(toolbar)

        # Section active par défaut : Activité.
        sidebar.select_row(self._activity_row)

    # -- navigation ----------------------------------------------------------

    def _on_nav_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        if row is None:
            return
        index = row.get_index()
        if 0 <= index < len(_SECTION_NAMES):
            self._content_stack.set_visible_child_name(_SECTION_NAMES[index])
            # Rafraîchit l'historique/logs à chaque ouverture de la section :
            # les syncs réalisées dans la section Activité sont aussitôt visibles.
            if _SECTION_NAMES[index] == "logs" and self._history_controller is not None:
                self._history_controller.refresh()

    # -- indicateur de connexion montre -------------------------------------

    def _build_garmin_bar(self) -> Gtk.Widget:
        """Barre bleue pleine largeur : indicateur montre + place à droite.

        La place à droite est réservée au bouton « ↻ Synchroniser » (Epic 3) ;
        pour l'instant un espaceur l'occupe.
        """
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        bar.add_css_class("garmin-bar")
        bar.set_hexpand(True)
        bar.set_margin_bottom(20)
        bar.append(self._build_watch_indicator())
        spacer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        spacer.set_hexpand(True)
        bar.append(spacer)
        return bar

    def _build_watch_indicator(self) -> Gtk.Widget:
        self._watch_dot = Gtk.Label(label="●")
        self._watch_dot.add_css_class("dim-label")
        self._watch_status_label = Gtk.Label(label="Montre déconnectée")
        self._watch_status_label.add_css_class("dim-label")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.append(self._watch_dot)
        box.append(self._watch_status_label)
        return box

    def _on_watch_status_changed(self, connected: bool) -> None:
        """Met à jour l'indicateur de la barre bleue (thread-safe).

        Voyant vert quand connecté, atténué (`dim-label`) quand déconnecté.
        """
        if connected:
            self._watch_dot.remove_css_class("dim-label")
            self._watch_dot.add_css_class("success")
            self._watch_status_label.remove_css_class("dim-label")
            self._watch_status_label.set_text("Montre connectée")
        else:
            self._watch_dot.remove_css_class("success")
            self._watch_dot.add_css_class("dim-label")
            self._watch_status_label.add_css_class("dim-label")
            self._watch_status_label.set_text("Montre déconnectée")

    # -- helpers de construction --------------------------------------------

    @staticmethod
    def _build_nav_row(title: str) -> Gtk.ListBoxRow:
        label = Gtk.Label(label=title)
        label.set_xalign(0.0)
        label.set_margin_start(12)
        label.set_margin_end(12)
        label.set_margin_top(10)
        label.set_margin_bottom(10)
        row = Gtk.ListBoxRow()
        row.set_child(label)
        return row

    @staticmethod
    def _build_section_placeholder(title: str) -> Gtk.Widget:
        """Placeholder simple pour les sections non couvertes (Epics 3-4)."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(24)
        box.set_margin_start(18)
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-2")
        title_label.set_halign(Gtk.Align.START)
        coming_label = Gtk.Label(label="À venir")
        coming_label.add_css_class("dim-label")
        coming_label.set_halign(Gtk.Align.START)
        box.append(title_label)
        box.append(coming_label)
        return box

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
