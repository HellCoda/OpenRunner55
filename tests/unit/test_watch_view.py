"""Tests unitaires de l'UI watch_view.

Seule la logique pure est testée (formatage du résumé d'envoi, formatage des
tailles de fichiers). L'instanciation des widgets GTK nécessite un display —
hors périmètre des tests unitaires (ADR-008 : tests UI = responsabilité UX,
cf. test_auth_view.py).
"""

from __future__ import annotations

import pytest

from openrunner55.sync.activities import SyncResult as ActivitySyncResult
from openrunner55.sync.workouts import SyncResult
from openrunner55.ui.watch_view import WatchView


@pytest.mark.unit
class TestFormatSummary:
    def test_full_success(self) -> None:
        result = SyncResult(total=3, success=3, failed=0, errors=[])
        assert WatchView._format_summary(result) == "3 workouts envoyés"

    def test_single_success(self) -> None:
        result = SyncResult(total=1, success=1, failed=0, errors=[])
        assert WatchView._format_summary(result) == "1 workout envoyé"

    def test_partial_failure_with_details(self) -> None:
        result = SyncResult(
            total=3,
            success=2,
            failed=1,
            errors=["workout 5: OSError: déconnexion USB"],
        )
        text = WatchView._format_summary(result)
        assert "2/3 envoyés" in text
        assert "1 échec" in text
        # détail préformaté affiché tel quel
        assert "workout 5: OSError: déconnexion USB" in text

    def test_total_failure_with_details(self) -> None:
        result = SyncResult(
            total=2,
            success=0,
            failed=2,
            errors=["workout 1: OSError: x", "workout 2: OSError: y"],
        )
        text = WatchView._format_summary(result)
        assert text.startswith("Échec de l'envoi.")
        assert "workout 1: OSError: x" in text
        assert "workout 2: OSError: y" in text

    def test_no_errors_omits_details_block(self) -> None:
        result = SyncResult(total=1, success=0, failed=1, errors=[])
        assert WatchView._format_summary(result) == "Échec de l'envoi."


@pytest.mark.unit
class TestFormatSize:
    """Formatage des tailles de fichiers (zone Montre, Epic 3)."""

    def test_bytes(self) -> None:
        assert WatchView._format_size(842) == "842 o"

    def test_zero(self) -> None:
        assert WatchView._format_size(0) == "0 o"

    def test_kibibytes(self) -> None:
        assert WatchView._format_size(2048) == "2 Ko"

    def test_mebibytes_one_decimal(self) -> None:
        assert WatchView._format_size(1_572_864) == "1,5 Mo"

    def test_mebibytes_round_number_no_decimal(self) -> None:
        assert WatchView._format_size(1024 * 1024) == "1 Mo"


@pytest.mark.unit
class TestFormatActivitySummary:
    """Résumé d'envoi Montre → GC (Epic 3) — succès / skippés / échecs."""

    def test_full_success(self) -> None:
        result = ActivitySyncResult(
            total=3, success=3, failed=0, errors=[], skipped=0
        )
        assert WatchView._format_activity_summary(result) == "3 fichiers envoyés"

    def test_single_success(self) -> None:
        result = ActivitySyncResult(
            total=1, success=1, failed=0, errors=[], skipped=0
        )
        assert WatchView._format_activity_summary(result) == "1 fichier envoyé"

    def test_success_with_skipped(self) -> None:
        result = ActivitySyncResult(
            total=5, success=2, failed=0, errors=[], skipped=3
        )
        assert (
            WatchView._format_activity_summary(result)
            == "2 fichiers envoyés · 3 skippés"
        )

    def test_only_skipped(self) -> None:
        result = ActivitySyncResult(
            total=2, success=0, failed=0, errors=[], skipped=2
        )
        # failed == 0 → branche succès ; success == 0 → pluriel « 0 fichiers »
        assert (
            WatchView._format_activity_summary(result)
            == "0 fichiers envoyés · 2 skippés"
        )

    def test_partial_failure_with_skipped_and_details(self) -> None:
        result = ActivitySyncResult(
            total=4,
            success=1,
            failed=2,
            errors=["file Activity/a.fit: OSError: x", "file Activity/b.fit: RuntimeError: y"],
            skipped=1,
        )
        text = WatchView._format_activity_summary(result)
        assert "1/4 envoyés" in text
        assert "2 échecs" in text
        assert "1 skippés" in text
        assert "file Activity/a.fit: OSError: x" in text

    def test_single_failure_wording(self) -> None:
        result = ActivitySyncResult(
            total=2, success=1, failed=1, errors=["file Activity/a.fit: E: x"], skipped=0
        )
        text = WatchView._format_activity_summary(result)
        assert "1 échec." in text
        assert "échecs" not in text.split("\n")[0]

    def test_total_failure_with_details(self) -> None:
        result = ActivitySyncResult(
            total=2,
            success=0,
            failed=2,
            errors=["file Activity/a.fit: OSError: x", "file Activity/b.fit: OSError: y"],
            skipped=0,
        )
        text = WatchView._format_activity_summary(result)
        assert text.startswith("Échec de l'envoi.")
        assert "file Activity/b.fit: OSError: y" in text
