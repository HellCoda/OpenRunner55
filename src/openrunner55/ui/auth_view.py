"""Écran de login GTK4 (couche UI, pré-authentification).

Conforme docs/conception/ux-design.md §4.4 : fenêtre centrée, formulaire
email/mot de passe, bouton "Se connecter" (suggested-action), spinner pendant
l'authentification, erreurs sous le formulaire.

Contraintes d'architecture (ADR-002, ADR-007) :
- L'UI n'importe jamais `garminconnect` directement : tout passe par
  l'Authenticator.
- Le login est un appel réseau long : exécuté dans un thread séparé, l'UI
  reste responsive. Le retour au thread GTK principal passe par
  `GLib.idle_add` — jamais de manipulation de widgets hors du thread GTK.
"""

from __future__ import annotations

import logging
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import GLib, GObject, Gtk

from openrunner55.auth.authenticator import Authenticator, GarminLoginError, GarminMFAError

_LOGGER = logging.getLogger(__name__)

MFA_MESSAGE = (
    "L'authentification multi-facteurs (MFA) n'est pas supportée. "
    "Désactivez-la dans vos paramètres Garmin Connect."
)
NETWORK_MESSAGE = "Impossible de contacter Garmin Connect. Vérifiez votre connexion Internet."


class AuthView(Gtk.Box):
    """Formulaire de connexion Garmin Connect.

    Émet le signal `authenticated` avec le client Garmin en payload dès que
    la connexion réussit.
    """

    __gsignals__ = {
        "authenticated": (GObject.SignalFlags.RUN_FIRST, None, (object,)),
    }

    def __init__(self, authenticator: Authenticator | None = None, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self._authenticator = authenticator or Authenticator()
        self._thread: threading.Thread | None = None
        self._build_ui()

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        # Conteneur centré : la vue occupe toute la fenêtre, le formulaire est centré.
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_size_request(420, -1)

        title = Gtk.Label(label="OpenRunner55")
        title.add_css_class("title-1")
        subtitle = Gtk.Label(label="Connectez-vous à Garmin Connect")
        subtitle.add_css_class("dim-label")
        self.append(title)
        self.append(subtitle)

        self.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

        # Email
        self._email_entry = Gtk.Entry()
        self._email_entry.set_placeholder_text("adresse@email.com")
        self._email_entry.set_input_purpose(Gtk.InputPurpose.EMAIL)
        self.append(self._email_entry)

        # Mot de passe — Gtk.PasswordEntry GTK4 inclut le toggle de visibilité
        self._password_entry = Gtk.PasswordEntry()
        self._password_entry.set_property("placeholder-text", "Mot de passe")
        self.append(self._password_entry)

        # Message d'erreur (caché tant qu'aucun échec)
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_wrap(True)
        self._error_label.set_justify(Gtk.Justification.CENTER)
        self._error_label.set_visible(False)
        self.append(self._error_label)

        # Bouton + spinner
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self._login_button = Gtk.Button(label="Se connecter")
        self._login_button.add_css_class("suggested-action")
        self._login_button.set_hexpand(True)
        self._spinner = Gtk.Spinner()
        self._spinner.set_visible(False)
        row.append(self._login_button)
        row.append(self._spinner)
        self.append(row)

        # État initial : bouton inactif tant que les champs sont vides (US-1.1)
        self._login_button.set_sensitive(False)
        self._email_entry.connect("changed", self._on_field_changed)
        self._password_entry.connect("changed", self._on_field_changed)
        self._login_button.connect("clicked", self._on_submit)

    # -- comportement --------------------------------------------------------

    def _on_field_changed(self, _widget) -> None:
        """Active le bouton seulement si email ET mot de passe sont remplis."""
        email = self._email_entry.get_text().strip()
        password = self._password_entry.get_text()
        self._login_button.set_sensitive(bool(email) and bool(password))

    def _on_submit(self, _button) -> None:
        email = self._email_entry.get_text().strip()
        password = self._password_entry.get_text()
        if not email or not password:
            return
        self._set_loading(True)
        self._error_label.set_visible(False)
        self._thread = threading.Thread(
            target=self._login_worker, args=(email, password), daemon=True
        )
        self._thread.start()

    def _login_worker(self, email: str, password: str) -> None:
        """Exécute le login hors du thread GTK (appel réseau long)."""
        try:
            client = self._authenticator.login(email, password)
            GLib.idle_add(self._on_login_success, client)
        except Exception as exc:
            GLib.idle_add(self._on_login_failure, exc)

    def _on_login_success(self, client) -> None:
        self._set_loading(False)
        self.emit("authenticated", client)

    def _on_login_failure(self, exc: Exception) -> None:
        self._set_loading(False)
        message = self.error_message(exc)
        self._error_label.set_text(message)
        self._error_label.set_visible(True)
        _LOGGER.warning("Échec de connexion : %s", exc)

    def _set_loading(self, loading: bool) -> None:
        """Désactive le formulaire et affiche le spinner pendant le login."""
        self._email_entry.set_sensitive(not loading)
        self._password_entry.set_sensitive(not loading)
        self._login_button.set_sensitive(not loading)
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()

    @staticmethod
    def error_message(exc: Exception) -> str:
        """Traduit une exception d'auth en message utilisateur (UX §4.4)."""
        if isinstance(exc, GarminMFAError):
            return MFA_MESSAGE
        if isinstance(exc, GarminLoginError):
            return str(exc)
        return NETWORK_MESSAGE
