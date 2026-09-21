"""Section Logs & Historique (couche UI, GTK4/libadwaita).

Conforme `docs/conception/ux-design.md` §4.2 : vue unique plein contenu, deux
zones superposées séparées par une poignée `Gtk.Paned` verticale fine —

- **haut** : tableau d'historique (une ligne par `SyncRecord`, détail dépliable
  au clic) ;
- **bas** : logs bruts monospace, filtrables par niveau (INFO/WARN/ERROR/Tous).

La vue délègue toute la logique de présentation au `HistoryController` (état,
filtre, parsing du détail) — les widgets GTK restent minces (ADR-002, ADR-008),
pattern miroir de `WatchView`. Aucun thread lancé par la vue : le controller est
synchrone (lectures SQLite instantanées, décision du brief).

Le chargement initial (`controller.refresh()`) est déclenché par la composition
root (`ui/app.py`) après construction, conformément au brief. La vue se contente
de s'abonner aux callbacks et de reconstruire ses listes.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

from openrunner55.ui.history_controller import HistoryController, SyncRecordDetail


class HistoryView(Gtk.Box):
    """Vue « Logs & Historique » : tableau d'historique (haut) + logs (bas)."""

    # Mapping direction → symbole affiché (↓ GC→Montre, ↑ Montre→GC).
    _DIRECTION_SYMBOLS = {"down": "↓", "up": "↑", "both": "⇅"}

    # Mapping statut → (texte affiché, classe CSS de couleur).
    _STATUS_DISPLAY = {
        "success": ("✓ Succès", "success"),
        "partial": ("⚠ Partiel", "warning"),
        "failed": ("✗ Échec", "error"),
    }

    # Mapping niveau de log → classe CSS de couleur (None = couleur normale).
    _LEVEL_CSS = {
        "WARN": "warning",
        "ERROR": "error",
        "DEBUG": "dim-label",
    }

    def __init__(self, controller: HistoryController, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self._controller = controller
        # Marge haute nulle : la vue s'aligne sur le haut de la barre latérale.
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self._build_ui()
        self._connect_controller()

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        paned.add_css_class("card")
        paned.set_hexpand(True)
        paned.set_vexpand(True)
        paned.set_wide_handle(False)  # poignée fine
        paned.set_position(280)  # hauteur initiale du tableau d'historique
        paned.set_resize_start_child(False)  # le haut reste fixe, les logs s'étendent
        paned.set_resize_end_child(True)
        paned.set_start_child(self._build_history_section())
        paned.set_end_child(self._build_logs_section())
        self.append(paned)

    def _build_history_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        header = Gtk.Label(label="Historique des synchronisations")
        header.add_css_class("title-2")
        header.set_halign(Gtk.Align.START)
        box.append(header)

        # État vide (visible tant qu'aucune sync n'est enregistrée).
        self._history_empty = Gtk.Label(label="Aucune synchronisation enregistrée")
        self._history_empty.add_css_class("dim-label")
        self._history_empty.set_halign(Gtk.Align.CENTER)
        self._history_empty.set_valign(Gtk.Align.CENTER)
        self._history_empty.set_vexpand(True)
        box.append(self._history_empty)

        self._history_list_box = Gtk.ListBox()
        self._history_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._history_scroll = Gtk.ScrolledWindow()
        self._history_scroll.set_vexpand(True)
        self._history_scroll.set_child(self._history_list_box)
        self._history_scroll.set_visible(False)
        box.append(self._history_scroll)

        return box

    def _build_logs_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        header = Gtk.Label(label="Logs d'opérations")
        header.add_css_class("title-2")
        header.set_halign(Gtk.Align.START)
        box.append(header)

        # Filtre par niveau : 3 ToggleButton groupés (INFO/WARN/ERROR) + « Tous ».
        # Groupés → un seul actif à la fois (comportement radio).
        filters = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        group: Gtk.ToggleButton | None = None
        for key, label in (("all", "Tous"), ("INFO", "INFO"), ("WARN", "WARN"), ("ERROR", "ERROR")):
            button = Gtk.ToggleButton(label=label)
            if group is None:
                group = button
                # Actif AVANT connexion du signal : pas de déclenchement au setup.
                button.set_active(True)
            else:
                button.set_group(group)
            button.connect("toggled", self._on_filter_toggled, key)
            filters.append(button)
        box.append(filters)

        # État vide (visible tant qu'aucun log ne correspond).
        self._logs_empty = Gtk.Label(label="Aucun log")
        self._logs_empty.add_css_class("dim-label")
        self._logs_empty.set_halign(Gtk.Align.CENTER)
        self._logs_empty.set_valign(Gtk.Align.CENTER)
        self._logs_empty.set_vexpand(True)
        box.append(self._logs_empty)

        self._logs_list_box = Gtk.ListBox()
        self._logs_list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._logs_scroll = Gtk.ScrolledWindow()
        self._logs_scroll.set_vexpand(True)
        self._logs_scroll.set_child(self._logs_list_box)
        self._logs_scroll.set_visible(False)
        box.append(self._logs_scroll)

        return box

    # -- connexion au controller ---------------------------------------------

    def _connect_controller(self) -> None:
        self._controller.on_records_changed(self._rebuild_history)
        self._controller.on_logs_changed(self._rebuild_logs)

    # -- rafraîchissements (thread GTK) --------------------------------------

    def _rebuild_history(self) -> None:
        """Notifié quand l'historique change : reconstruit le tableau."""
        self._history_list_box.remove_all()
        records = self._controller.records
        self._history_empty.set_visible(not records)
        self._history_scroll.set_visible(bool(records))
        for record in records:
            self._history_list_box.append(self._build_history_row(record))

    def _rebuild_logs(self) -> None:
        """Notifié quand les logs changent (ou le filtre) : reconstruit la liste."""
        self._logs_list_box.remove_all()
        logs = self._controller.logs
        self._logs_empty.set_visible(not logs)
        self._logs_scroll.set_visible(bool(logs))
        for log in logs:
            self._logs_list_box.append(self._build_log_row(log))

    # -- construction des lignes d'historique --------------------------------

    def _build_history_row(self, record) -> Gtk.ListBoxRow:
        detail = self._controller.parse_record(record)

        summary = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        summary.set_margin_top(6)
        summary.set_margin_bottom(6)
        summary.set_margin_start(8)
        summary.set_margin_end(8)

        date_label = Gtk.Label(label=HistoryController.format_timestamp(record.timestamp))
        date_label.add_css_class("dim-label")
        date_label.set_halign(Gtk.Align.START)
        date_label.set_width_chars(16)
        summary.append(date_label)

        direction_label = Gtk.Label(label=self._direction_symbol(record.direction))
        summary.append(direction_label)

        ratio_label = Gtk.Label(label=f"{record.file_count}/{detail.total}")
        ratio_label.set_width_chars(6)
        summary.append(ratio_label)

        status_text, status_css = self._status_display(record.status)
        status_label = Gtk.Label(label=status_text)
        status_label.set_halign(Gtk.Align.START)
        if status_css:
            status_label.add_css_class(status_css)
        summary.append(status_label)

        # Détail dépliable (Revealer), révélé/toggled au clic sur la ligne.
        revealer = Gtk.Revealer()
        revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        revealer.set_reveal_child(False)
        revealer.set_child(self._build_detail_box(detail))

        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        container.append(summary)
        container.append(revealer)

        row = Gtk.ListBoxRow()
        row.set_activatable(True)
        row.set_child(container)
        row.connect("activate", self._on_history_row_activate, revealer)
        return row

    def _build_detail_box(self, detail: SyncRecordDetail) -> Gtk.Widget:
        """Construit le détail d'une sync : fichiers réussis, erreurs, skippés."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_margin_start(32)
        box.set_margin_end(8)
        box.set_margin_bottom(8)

        for name in detail.files:
            label = Gtk.Label(label=f"✓ {name}")
            label.set_xalign(0.0)
            box.append(label)

        for message in detail.errors:
            label = Gtk.Label(label=f"✗ {message}")
            label.set_xalign(0.0)
            label.set_wrap(True)
            label.set_selectable(True)
            label.add_css_class("error")
            box.append(label)

        if detail.skipped:
            label = Gtk.Label(label=f"{detail.skipped} skippé(s)")
            label.set_xalign(0.0)
            label.add_css_class("dim-label")
            box.append(label)

        return box

    # -- construction des lignes de log --------------------------------------

    def _build_log_row(self, log) -> Gtk.ListBoxRow:
        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row_box.set_margin_start(8)
        row_box.set_margin_end(8)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        timestamp_label = Gtk.Label(label=f"[{log.timestamp}]")
        timestamp_label.add_css_class("monospace")
        timestamp_label.add_css_class("dim-label")
        row_box.append(timestamp_label)

        level_label = Gtk.Label(label=f"[{log.level}]")
        level_label.add_css_class("monospace")
        level_css = self._level_css(log.level)
        if level_css:
            level_label.add_css_class(level_css)
        row_box.append(level_label)

        message_label = Gtk.Label(label=log.message)
        message_label.add_css_class("monospace")
        message_label.set_xalign(0.0)
        message_label.set_wrap(True)
        message_label.set_selectable(True)
        message_label.set_hexpand(True)
        row_box.append(message_label)

        row = Gtk.ListBoxRow()
        row.set_activatable(False)
        row.set_child(row_box)
        return row

    # -- gestionnaires de signaux --------------------------------------------

    def _on_history_row_activate(self, _row: Gtk.ListBoxRow, revealer: Gtk.Revealer) -> None:
        """Bascule l'affichage du détail au clic sur une ligne d'historique."""
        revealer.set_reveal_child(not revealer.get_reveal_child())

    def _on_filter_toggled(self, button: Gtk.ToggleButton, key: str) -> None:
        """Applique le filtre quand un bouton devient actif (groupé, un seul actif)."""
        if button.get_active():
            level = None if key == "all" else key
            self._controller.set_log_level_filter(level)

    # -- formatage -----------------------------------------------------------

    @classmethod
    def _direction_symbol(cls, direction: str) -> str:
        return cls._DIRECTION_SYMBOLS.get(direction, direction)

    @classmethod
    def _status_display(cls, status: str) -> tuple[str, str | None]:
        return cls._STATUS_DISPLAY.get(status, (status, None))

    @classmethod
    def _level_css(cls, level: str) -> str | None:
        return cls._LEVEL_CSS.get(level)
