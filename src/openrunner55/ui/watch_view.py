"""Section Activité (couche UI, GTK4/libadwaita).

Conforme `docs/conception/ux-design.md` §4.1 : split horizontal 40/60 entre la
zone Garmin Connect (gauche, fonctionnelle) et la zone Montre (droite,
placeholder). Les deux zones sont regroupées dans **un seul panneau unifié**
(classe `.card`) avec un séparateur vertical fin au milieu — pas de deux cartes
flottantes séparées par une poignée de `Gtk.Paned`.

La vue délègue toute la logique de présentation au `WorkoutsController` — les
widgets GTK restent minces (ADR-002, ADR-008).

Threading (brief Epic 2, option A) : la vue ne lance aucun thread elle-même.
Elle appelle `fetch_workouts_async` / `push_workouts_async` du controller, qui
lancent les threads et marshallent les callbacks vers le thread GTK via le
scheduler (`GLib.idle_add`) injecté dans le controller. Les handlers de la vue
s'exécutent donc toujours sur le thread GTK.
"""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk

from openrunner55.sync.workouts import SyncResult
from openrunner55.ui.workouts_controller import WorkoutsController


class WatchView(Gtk.Box):
    """Vue « Activité » : zone GC workouts (gauche) + zone Montre (droite)."""

    def __init__(self, controller: WorkoutsController, **kwargs) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0, **kwargs)
        self._controller = controller
        self._check_by_id: dict[int, Gtk.CheckButton] = {}
        self._syncing = False
        # Marge haute nulle : le panneau s'aligne sur le haut de la barre latérale.
        self.set_margin_bottom(18)
        self.set_margin_start(18)
        self.set_margin_end(18)
        self._build_ui()
        self._connect_controller()
        # Chargement initial de la liste (post-auth).
        self._controller.fetch_workouts_async(self._on_fetch_done, self._on_fetch_error)

    # -- construction --------------------------------------------------------

    def _build_ui(self) -> None:
        # Panneau unifié `.card` avec une poignée de redimensionnement fine
        # (curseur) entre les deux zones, au lieu d'un séparateur figé.
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.add_css_class("card")
        paned.set_hexpand(True)
        paned.set_vexpand(True)
        paned.set_wide_handle(False)  # poignée fine, pas de bande épaisse
        paned.set_position(360)  # position initiale ≈ 40 % d'une fenêtre de 900 px
        paned.set_resize_start_child(False)
        paned.set_resize_end_child(True)
        paned.set_start_child(self._build_gc_section())
        paned.set_end_child(self._build_watch_section())
        self.append(paned)

    @staticmethod
    def _build_header(title: str, subtitle: str) -> tuple[Gtk.Widget, Gtk.Label]:
        """Construit un en-tête de section cohérent (titre + sous-titre grisé).

        :returns: (widget en-tête, label du sous-titre pour mise à jour éventuelle)
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("title-2")
        title_label.set_halign(Gtk.Align.START)
        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.add_css_class("dim-label")
        subtitle_label.set_halign(Gtk.Align.START)
        box.append(title_label)
        box.append(subtitle_label)
        return box, subtitle_label

    def _build_gc_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_size_request(280, -1)  # largeur minimale (le Paned gère le reste)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        header, self._subtitle = self._build_header("Garmin Connect", "Workouts (0)")
        box.append(header)

        # Spinner (centré) pendant le chargement.
        self._spinner = Gtk.Spinner()
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        self._spinner.set_vexpand(True)
        box.append(self._spinner)

        # Liste des workouts (checkbox + nom).
        self._list_box = Gtk.ListBox()
        self._list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._list_scroll = Gtk.ScrolledWindow()
        self._list_scroll.set_vexpand(True)
        self._list_scroll.set_child(self._list_box)
        self._list_scroll.set_visible(False)
        box.append(self._list_scroll)

        # Message d'erreur de chargement (caché par défaut).
        self._error_label = Gtk.Label()
        self._error_label.add_css_class("error")
        self._error_label.set_wrap(True)
        self._error_label.set_visible(False)
        box.append(self._error_label)

        # Bouton d'envoi.
        self._send_button = Gtk.Button(label="Envoyer (0)")
        self._send_button.add_css_class("suggested-action")
        self._send_button.set_sensitive(False)
        self._send_button.connect("clicked", self._on_send_clicked)
        box.append(self._send_button)

        # Barre de progression (révélée pendant l'envoi).
        self._progress_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._progress_box.set_visible(False)
        self._progress_label = Gtk.Label()
        self._progress_label.set_wrap(True)
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_box.append(self._progress_label)
        self._progress_box.append(self._progress_bar)
        box.append(self._progress_box)

        # Résumé de l'envoi (révélé après coup).
        self._summary_label = Gtk.Label()
        self._summary_label.set_wrap(True)
        self._summary_label.set_visible(False)
        box.append(self._summary_label)

        return box

    def _build_watch_section(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_hexpand(True)
        box.set_margin_top(12)
        box.set_margin_bottom(12)
        box.set_margin_start(12)
        box.set_margin_end(12)

        header, _ = self._build_header("Montre - FR55", "Activités")
        box.append(header)

        self._watch_placeholder = Gtk.Label()
        self._watch_placeholder.add_css_class("dim-label")
        self._watch_placeholder.set_halign(Gtk.Align.CENTER)
        self._watch_placeholder.set_valign(Gtk.Align.CENTER)
        self._watch_placeholder.set_vexpand(True)
        box.append(self._watch_placeholder)

        self._update_watch_placeholder()
        return box

    # -- connexion au controller --------------------------------------------

    def _connect_controller(self) -> None:
        self._controller.on_workouts_changed(self._refresh_workouts)
        self._controller.on_selection_changed(self._refresh_selection)
        self._controller.on_sending_state_changed(self._refresh_sending)

    # -- rafraîchissements (thread GTK) -------------------------------------

    def _refresh_workouts(self) -> None:
        """Notifié quand la liste ou l'état de chargement change."""
        if self._controller.is_loading:
            self._spinner.set_visible(True)
            self._spinner.start()
            self._list_scroll.set_visible(False)
        else:
            self._spinner.stop()
            self._spinner.set_visible(False)
            self._list_scroll.set_visible(True)
            self._rebuild_list()
        self._update_subtitle()
        self._refresh_send_button()

    def _refresh_selection(self) -> None:
        """Notifié quand la sélection change : synchronise les checkboxes."""
        self._sync_checkboxes()
        self._refresh_send_button()

    def _refresh_sending(self) -> None:
        """Notifié quand l'état de l'envoi ou la connexion montre change."""
        self._refresh_send_button()
        self._update_progress()
        self._update_summary()
        self._update_watch_placeholder()

    def _refresh_send_button(self) -> None:
        count = self._controller.selected_count
        self._send_button.set_label(f"Envoyer ({count})")
        self._send_button.set_sensitive(self._controller.can_send)

    def _update_subtitle(self) -> None:
        count = len(self._controller.workouts)
        self._subtitle.set_text(f"Workouts ({count})")

    def _update_progress(self) -> None:
        progress = self._controller.progress
        if self._controller.is_sending and progress is not None:
            current, total, name = progress
            if name:
                self._progress_label.set_text(f"Workout {current}/{total} — {name}")
            else:
                self._progress_label.set_text(f"Envoi en cours… ({total} workouts)")
            fraction = current / total if total else 0.0
            self._progress_bar.set_fraction(fraction)
            self._progress_bar.set_text(f"{int(fraction * 100)} %")
            self._progress_box.set_visible(True)
        else:
            self._progress_box.set_visible(False)

    def _update_summary(self) -> None:
        if self._controller.is_sending:
            self._summary_label.set_visible(False)
            return
        result = self._controller.last_result
        if result is None:
            self._summary_label.set_visible(False)
            return
        self._summary_label.set_text(self._format_summary(result))
        self._summary_label.set_visible(True)

    def _update_watch_placeholder(self) -> None:
        if self._controller.watch_connected:
            self._watch_placeholder.set_text("Réservé à l'Epic 3")
        else:
            self._watch_placeholder.set_text("Branchez votre montre FR55 en USB")

    # -- construction de la liste -------------------------------------------

    def _rebuild_list(self) -> None:
        """Reconstruit la liste depuis `controller.workouts`."""
        self._list_box.remove_all()
        self._check_by_id.clear()
        for workout in self._controller.workouts:
            label = workout.name or "(sans nom)"
            check = Gtk.CheckButton(label=label)
            # set_active avant de connecter « toggled » pour éviter le rebouclage.
            check.set_active(workout.workout_id in self._controller.selected)
            check.connect("toggled", self._on_check_toggled, workout.workout_id)
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            row.set_child(check)
            self._list_box.append(row)
            self._check_by_id[workout.workout_id] = check

    def _sync_checkboxes(self) -> None:
        """Aligne l'état des checkboxes sur `controller.selected` (sans reboucler)."""
        self._syncing = True
        try:
            for workout_id, check in self._check_by_id.items():
                check.set_active(workout_id in self._controller.selected)
        finally:
            self._syncing = False

    # -- gestionnaires de signaux -------------------------------------------

    def _on_check_toggled(self, check: Gtk.CheckButton, workout_id: int) -> None:
        if self._syncing:
            return
        self._controller.toggle_selection(workout_id)

    def _on_send_clicked(self, _button: Gtk.Button) -> None:
        self._controller.push_workouts_async(
            on_progress=lambda *_: None,
            on_done=lambda _result: None,
            on_error=self._on_push_error,
        )

    # -- callbacks par-appel (erreurs uniquement) ---------------------------

    def _on_fetch_done(self, _workouts) -> None:
        self._error_label.set_visible(False)

    def _on_fetch_error(self, exc: Exception) -> None:
        # Message générique : l'exception brute peut porter des détails réseau
        # ou d'auth ; on n'expose qu'une consigne utilisateur (cohérent UX §4.4).
        self._error_label.set_text(
            "Impossible de charger les workouts Garmin Connect. "
            "Vérifiez votre connexion Internet."
        )
        self._error_label.set_visible(True)

    def _on_push_error(self, exc: Exception) -> None:
        # Erreur fatale (ex. montre débranchée avant le premier download).
        self._summary_label.set_text(f"Échec de l'envoi.\n{exc}")
        self._summary_label.set_visible(True)

    # -- formatage -----------------------------------------------------------

    @staticmethod
    def _format_summary(result: SyncResult) -> str:
        """Formate le résumé d'un envoi (UX §4.1, parcours C).

        - succès total : « N workouts envoyés »
        - échec partiel : « X/N envoyés. Y échecs. » + détail par erreur
        - échec total : « Échec de l'envoi. » + détail par erreur

        `SyncResult.errors` contient des chaînes préformatées, affichées telles
        quelles (contrat backend figé).
        """
        if result.failed == 0:
            if result.success == 1:
                return "1 workout envoyé"
            return f"{result.success} workouts envoyés"
        if result.success == 0:
            text = "Échec de l'envoi."
        else:
            failures = "échec" if result.failed == 1 else "échecs"
            text = f"{result.success}/{result.total} envoyés. {result.failed} {failures}."
        if result.errors:
            text += "\n" + "\n".join(result.errors)
        return text
