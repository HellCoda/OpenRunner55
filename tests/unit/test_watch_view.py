"""Tests unitaires de l'UI watch_view.

Seule la logique pure est testée (formatage du résumé d'envoi, formatage des
tailles de fichiers). L'instanciation des widgets GTK nécessite un display —
hors périmètre des tests unitaires (ADR-008 : tests UI = responsabilité UX,
cf. test_auth_view.py).
"""

from __future__ import annotations

import pytest

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
