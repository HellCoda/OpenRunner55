"""Section « Compte & Paramètres » (couche UI, post-authentification).

Conforme `docs/conception/ux-design.md` §4.3 : trois cartes informatives
empilées verticalement —

- **Compte Garmin Connect** : email en lecture seule, statut de connexion,
  action « Se déconnecter » (dialogue de confirmation destructif) ;
- **Stockage local** : chemins réels du tokenstore et de la base, trousseau ;
- **Application** : version, licence, lien GitHub.

Contraintes d'architecture (ADR-002) :
- La vue n'importe jamais `garminconnect` directement : les dépendances
  (`Authenticator`, `client`) sont injectées au constructeur, comme `auth_view`.
- `delete_credentials()` est un appel **local** (keyring + suppression du
  tokenstore) : aucun thread nécessaire, contrairement au login d'`auth_view`.
  La vue émet simplement le signal `logged_out` ; c'est la composition root
  (`ui/app.py`) qui stoppe le détecteur USB et rebascule sur l'écran de login.
"""

from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GObject, Gtk

from openrunner55 import __version__
from openrunner55.auth.authenticator import TOKENSTORE_FILE, Authenticator
from openrunner55.store.database import DEFAULT_DB_PATH

_LOGGER = logging.getLogger(__name__)

# Licence (décision DP validée par Franck le 22/09 — constante centralisée).
LICENSE = "MIT"

GITHUB_URL = "https://github.com/HellCoda/OpenRunner55"

_KEYRING_DISPLAY = "GNOME Keyring (session)"

_DISCONNECT_HEADING = "Se déconnecter ?"
_DISCONNECT_BODY = (
    "Les identifiants seront supprimés du trousseau et le tokenstore sera effacé."
)


class AccountView(Gtk.Box):
    """Vue « Compte & Paramètres » : 3 cartes + action de déconnexion.

    Émet le signal `logged_out` (sans payload) après une déconnexion confirmée.
    """

    __gsignals__ = {
        "logged_out": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, authenticator: Authenticator, client=None, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12, **kwargs)
        self._authenticator = authenticator
        self._client = client
        self.set_hexpand(True)
        self.set_margin_top(18)
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self._build_ui()

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_account_card()
        self._build_storage_card()
        self._build_app_card()

    def _add_card(self, title: str) -> Gtk.Box:
        """Crée une carte (fond `card` + padding interne) et retourne son contenu."""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        card.set_hexpand(True)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-2")
        title_label.set_halign(Gtk.Align.START)
        content.append(title_label)

        card.append(content)
        self.append(card)
        return content

    def _build_account_card(self) -> None:
        content = self._add_card("Compte Garmin Connect")

        # Email en lecture seule — source : keyring, fallback `client.display_name`.
        email = self._authenticator.get_email() or getattr(self._client, "display_name", None) or "—"
        email_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        email_row.append(Gtk.Image.new_from_icon_name("user-info-symbolic"))
        email_label = Gtk.Label(label=email)
        email_label.set_xalign(0.0)
        email_label.set_selectable(True)
        email_label.set_hexpand(True)
        email_row.append(email_label)
        content.append(email_row)

        # Statut de connexion (token non expiré → connecté).
        status_label = Gtk.Label()
        status_label.set_xalign(0.0)
        if Authenticator.is_authenticated(self._client):
            status_label.set_text("● Connecté")
            status_label.add_css_class("success")
        else:
            status_label.set_text("○ Déconnecté")
            status_label.add_css_class("dim-label")
        content.append(status_label)

        # Action destructive : déconnexion après confirmation.
        disconnect_button = Gtk.Button(label="Se déconnecter")
        disconnect_button.add_css_class("destructive-action")
        disconnect_button.set_halign(Gtk.Align.START)
        disconnect_button.connect("clicked", self._on_disconnect_clicked)
        content.append(disconnect_button)

    def _build_storage_card(self) -> None:
        content = self._add_card("Stockage local")
        content.append(
            self._build_info_row("Tokenstore", str(TOKENSTORE_FILE), monospace=True)
        )
        content.append(
            self._build_info_row("Base de données", str(DEFAULT_DB_PATH), monospace=True)
        )
        content.append(self._build_info_row("Trousseau", _KEYRING_DISPLAY))

    def _build_app_card(self) -> None:
        content = self._add_card("Application")
        content.append(self._build_info_row("Version", __version__))
        content.append(self._build_info_row("Licence", LICENSE))
        link = Gtk.LinkButton.new_with_label(GITHUB_URL, "GitHub")
        link.set_halign(Gtk.Align.START)
        content.append(link)

    @staticmethod
    def _build_info_row(label_text: str, value_text: str, *, monospace: bool = False) -> Gtk.Box:
        """Ligne « libellé / valeur » (dim-label à gauche, valeur alignée à droite)."""
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        label = Gtk.Label(label=label_text)
        label.add_css_class("dim-label")
        label.set_halign(Gtk.Align.START)
        label.set_valign(Gtk.Align.START)
        label.set_width_chars(16)
        value = Gtk.Label(label=value_text)
        value.set_xalign(0.0)
        value.set_hexpand(True)
        value.set_wrap(True)
        if monospace:
            value.add_css_class("monospace")
            value.set_selectable(True)
        row.append(label)
        row.append(value)
        return row

    # -- déconnexion ---------------------------------------------------------

    def _on_disconnect_clicked(self, _button: Gtk.Button) -> None:
        """Ouvre le dialogue de confirmation de déconnexion."""
        dialog = Adw.AlertDialog(
            heading=_DISCONNECT_HEADING,
            body=_DISCONNECT_BODY,
        )
        dialog.add_response("cancel", "Annuler")
        dialog.add_response("disconnect", "Se déconnecter")
        dialog.set_response_appearance("disconnect", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.choose(self.get_root(), None, self._on_disconnect_choice, None)

    def _on_disconnect_choice(self, dialog: Adw.AlertDialog, result, _user_data) -> None:
        """Applique la déconnexion si l'utilisateur a confirmé."""
        try:
            response = dialog.choose_finish(result)
        except Exception as exc:  # dialogue fermé (Échap) → aucune action
            _LOGGER.debug("Dialogue de déconnexion fermé sans réponse : %s", exc)
            return
        if response != "disconnect":
            return
        self._authenticator.delete_credentials()
        _LOGGER.info("Déconnexion : credentials et tokenstore supprimés")
        self.emit("logged_out")
